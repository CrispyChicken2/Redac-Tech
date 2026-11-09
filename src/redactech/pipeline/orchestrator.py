"""A0 - pipeline orchestrator: a hand-written state machine over ``RunState.stage``.

Stages and the checkpoints where the pipeline stops for the writer::

    indexed -> ops_proposed        (checkpoint: operations)   A1 index + baseline, A2 operations
    ops_proposed -> ops_validated                             ``validate_ops``
    ops_validated -> zones_proposed                           ``propose_zones`` (A4)
    zones_proposed -> zones_validated -> proposals_ready      ``validate_zones`` (A5 + A7)
    proposals_ready -> reviewed    (checkpoint: proposals)   ``decide`` / ``reject``
    reviewed -> written                                       ``write`` (A11)

Every step is saved to ``<runs>/<run id>/state.json`` (pydantic JSON, UTF-8); ``Run.load``
resumes exactly. Nothing is written to a data module without a decision: ``write`` refuses
while a proposal is still ``proposed`` (flag-only illustration proposals change nothing and are
excluded) and while no versioning policy has been chosen. ``auto_accept`` exists for tests and
the hidden CLI option only. This module never imports streamlit.

Alternatives found after a rejection (or by the BREX retry loop) have DERIVED operations
(own id, merged parameters); they are appended to ``state.operations`` so that the checker and
the writer apply the variant. ``decisions_log`` also receives events (``skipped_readonly``,
``alternative``, ``needs_manual_edit``, ``written`` ...), each with a timestamp.
"""

from __future__ import annotations

import datetime
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, model_validator

from redactech.agents import a1_indexer, a2_mapping, a4_locator, a5_preparer, a7_checker
from redactech.agents.a11_writer import WriteRefused, WriteResult, write
from redactech.config import load_config
from redactech.models import CheckResult, Operation, Proposal, RunState, VersionPolicy, Zone
from redactech.s1000d import versioning
from redactech.s1000d.index import CorpusIndex, build_index, ref_key
from redactech.sources import workspace as wsmod

Mode = Literal["none", "in_work", "new_issue"]
STAGES_FOR_REVIEW = ("proposals_ready", "reviewed")
DECISIONS = ("accepted", "edited", "rejected", "pending_client")
STATE_FILE = "state.json"
REQUEST_FILE = "request.json"


class PipelineError(RuntimeError):
    """A step was called at the wrong stage, or a decision is not allowed."""


class RunRequest(BaseModel):
    """What the writer asked for: a mapping file OR a form, and optionally a policy."""

    mapping: str | None = None
    form: dict[str, Any] | None = None
    version_policy: Mode | None = None
    auto_accept: bool = False  # tests and the hidden CLI option only

    @model_validator(mode="after")
    def _one_source(self) -> RunRequest:
        if (self.mapping is None) == (self.form is None):
            raise ValueError("give exactly one of mapping and form")
        return self


def is_derived(op: Operation, operations: list[Operation]) -> bool:
    """Is ``op`` an alternative's derived operation (``<base id>-a<n>-<zone id>``)?"""
    return any(op.id.startswith(other.id + "-a") for other in operations if other.id != op.id)


class Run:
    """One run: its folder, its state and the lazily rebuilt index."""

    def __init__(
        self,
        run_dir: Path,
        state: RunState,
        request: RunRequest,
        clock: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.state = state
        self.request = request
        self._clock = clock or datetime.datetime.now
        self._index: CorpusIndex | None = None
        self._trace = load_config().trace

    # --- creation, persistence --------------------------------------------------------------------

    @classmethod
    def start(
        cls,
        request: RunRequest,
        workspace_path: Path | str,
        runs_dir: Path | str,
        clock: Callable[[], datetime.datetime] | None = None,
        token: str | None = None,
    ) -> Run:
        """New run: index + baseline (A1), operations (A2); stops at ``ops_proposed``."""
        now = (clock or datetime.datetime.now)()
        run_id = f"{now:%Y%m%d-%H%M%S}-{token or secrets.token_hex(2)}"
        run_dir = Path(runs_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        workspace_file = Path(workspace_path).resolve()
        index, baseline = a1_indexer.run(wsmod.load_workspace(workspace_file))
        if request.mapping is not None:
            request = request.model_copy(update={"mapping": str(Path(request.mapping).resolve())})
        state = RunState(
            run_id=run_id,
            workspace=str(workspace_file),
            stage="indexed",
            baseline=baseline,
            operations=[],
            zones=[],
            proposals=[],
            decisions_log=[],
        )
        run = cls(run_dir, state, request, clock)
        run._index = index
        (run_dir / REQUEST_FILE).write_text(request.model_dump_json(indent=2), encoding="utf-8")
        run._save()
        if request.mapping is not None:
            operations = a2_mapping.mapping_operations(request.mapping)
        else:
            operations = a2_mapping.from_form(request.form or {})
        state.operations = operations
        state.stage = "ops_proposed"
        if request.version_policy is not None:
            suggestion = versioning.suggest_policy(operations)
            state.version_policy = suggestion.model_copy(update={"mode": request.version_policy})
        run._log(event="ops_proposed", operations=[o.id for o in operations])
        run._save()
        return run

    @classmethod
    def load(
        cls, run_dir: Path | str, clock: Callable[[], datetime.datetime] | None = None
    ) -> Run:
        """Resume a run exactly where it was saved."""
        folder = Path(run_dir)
        state = RunState.model_validate_json((folder / STATE_FILE).read_text(encoding="utf-8"))
        request = RunRequest.model_validate_json(
            (folder / REQUEST_FILE).read_text(encoding="utf-8")
        )
        return cls(folder, state, request, clock)

    def _save(self) -> None:
        (self.run_dir / STATE_FILE).write_text(
            self.state.model_dump_json(indent=2), encoding="utf-8"
        )

    def _log(self, **entry: Any) -> None:
        entry["time"] = self._clock().isoformat(timespec="seconds")
        self.state.decisions_log.append(entry)

    @property
    def index(self) -> CorpusIndex:
        if self._index is None:
            self._index = build_index(wsmod.load_workspace(self.state.workspace))
        return self._index

    def _need(self, *stages: str) -> None:
        if self.state.stage not in stages:
            wanted = " or ".join(stages)
            raise PipelineError(f"stage is {self.state.stage!r}, this step needs {wanted!r}")

    # --- operations, zones, proposals -------------------------------------------------------------

    def base_operations(self) -> list[Operation]:
        ops = self.state.operations
        return [o for o in ops if not is_derived(o, ops)]

    def suggestion(self) -> VersionPolicy:
        """The versioning policy suggested by the operations (with its reasons)."""
        return versioning.suggest_policy(self.base_operations())

    def validate_ops(self, op_ids: list[str] | None = None) -> None:
        """Checkpoint: the writer confirms the operations (or keeps only ``op_ids``)."""
        self._need("ops_proposed")
        if op_ids is not None:
            known = {o.id for o in self.state.operations}
            unknown = sorted(set(op_ids) - known)
            if unknown:
                raise PipelineError(f"unknown operation(s): {', '.join(unknown)}")
            dropped = [o.id for o in self.state.operations if o.id not in set(op_ids)]
            self.state.operations = [o for o in self.state.operations if o.id in set(op_ids)]
            if dropped:
                self._log(event="operations_dropped", operations=dropped)
        self.state.stage = "ops_validated"
        self._log(event="ops_validated", operations=[o.id for o in self.state.operations])
        self._save()

    def propose_zones(self) -> None:
        """A4: where does each operation apply? Read-only occurrences are logged, not zoned."""
        self._need("ops_validated")
        zones: list[Zone] = []
        for op in self.state.operations:
            try:
                located = a4_locator.locate(op, self.index)
            except a4_locator.LocateError as exc:
                self._log(event="locate_error", operation=op.id, reason=str(exc))
                continue
            zones.extend(located.zones)
            for skipped in located.skipped_readonly:
                self._log(
                    event="skipped_readonly",
                    operation=op.id,
                    document=ref_key(skipped.ref),
                    kind=skipped.kind,
                    reason=skipped.reason,
                )
        self.state.zones = zones
        self.state.stage = "zones_proposed"
        self._log(event="zones_proposed", zones=[z.id for z in zones])
        self._save()

    def validate_zones(self, zone_ids: list[str] | None = None) -> None:
        """Checkpoint: confirm the zones (A4 first if needed), then A5 + A7; stops at review."""
        if self.state.stage == "ops_validated":
            self.propose_zones()
        self._need("zones_proposed")
        if zone_ids is not None:
            unknown = sorted(set(zone_ids) - {z.id for z in self.state.zones})
            if unknown:
                raise PipelineError(f"unknown zone(s): {', '.join(unknown)}")
            self.state.zones = [z for z in self.state.zones if z.id in set(zone_ids)]
        self.state.stage = "zones_validated"
        self._save()
        proposals: list[Proposal] = []
        operations: list[Operation] = []
        for op in self.state.operations:
            op_zones = [z for z in self.state.zones if z.operation_id == op.id]
            if not op_zones:
                operations.append(op)
                continue
            checked = a5_preparer.prepare_checked(
                op,
                op_zones,
                self.index,
                self.state.baseline,
                max_rule_retries=self._trace.max_rule_retries,
            )
            proposals.extend(checked.proposals)
            operations.extend(checked.all_operations)
            for error in checked.errors:
                self._log(event="prepare_error", operation=op.id, reason=error)
        self.state.operations = operations
        self.state.proposals = proposals
        self.state.stage = "proposals_ready"
        self._log(event="proposals_ready", proposals=[p.id for p in proposals])
        self._save()

    def run_to_review(self) -> None:
        """Convenience: confirm operations and zones and stop at the proposals checkpoint."""
        self.validate_ops()
        self.validate_zones()

    # --- decisions --------------------

    def _zone_of(self, proposal: Proposal) -> Zone | None:
        return next((z for z in self.state.zones if z.id == proposal.zone_id), None)

    def _operation(self, op_id: str) -> Operation:
        found = next((o for o in self.state.operations if o.id == op_id), None)
        if found is None:
            raise PipelineError(f"unknown operation {op_id}")
        return found

    def _base_operation(self, op_id: str) -> Operation:
        for base in self.base_operations():
            if op_id == base.id or op_id.startswith(base.id + "-a"):
                return base
        raise PipelineError(f"unknown operation {op_id}")

    def _proposal(self, proposal_id: str) -> Proposal:
        found = next((p for p in self.state.proposals if p.id == proposal_id), None)
        if found is None:
            raise PipelineError(f"unknown proposal {proposal_id}")
        return found

    def _replace(self, proposal: Proposal) -> None:
        self.state.proposals = [
            proposal if p.id == proposal.id else p for p in self.state.proposals
        ]

    def _is_flag(self, proposal: Proposal) -> bool:
        zone = self._zone_of(proposal)
        return zone is not None and zone.kind == "illustration"

    def _refresh_stage(self) -> None:
        pending = [
            p for p in self.state.proposals if p.status == "proposed" and not self._is_flag(p)
        ]
        self.state.stage = "proposals_ready" if pending else "reviewed"

    @staticmethod
    def _introduced(checks: list[CheckResult], errors_only: bool = False) -> list[CheckResult]:
        return [
            c
            for c in checks
            if not c.ok
            and c.origin == "introduced"
            and (c.severity == "error" or not errors_only)
        ]

    def decide(
        self,
        proposal_id: str,
        status: str,
        comment: str | None = None,
        edited_xml: str | None = None,
        actor: str = "user",
    ) -> Proposal:
        """Record a decision (accepted | edited | rejected | pending_client) in the log."""
        self._need(*STAGES_FOR_REVIEW)
        if status not in DECISIONS:
            raise PipelineError(f"unknown decision {status!r} (expected one of {DECISIONS})")
        proposal = self._proposal(proposal_id)
        if proposal.status == "blocked_by_rule" and status != "pending_client":
            raise PipelineError(f"{proposal_id} is blocked by a business rule: ask the customer")
        update: dict[str, Any] = {"status": status, "reviewer_comment": comment}
        if status == "accepted" and self._introduced(proposal.checks, True):
            raise PipelineError(f"{proposal_id} introduces errors: edit it or reject it")
        if status == "edited":
            if not edited_xml or not edited_xml.strip():
                raise PipelineError("an edited decision needs the edited XML")
            zone = self._zone_of(proposal)
            candidate = proposal.model_copy(update={**update, "edited_xml": edited_xml})
            if zone is None:
                raise PipelineError(f"unknown zone of {proposal_id}")
            checks = a7_checker.check_proposal(
                candidate,
                self.index,
                self.state.baseline,
                operation=self._operation(proposal.operation_id),
                zone=zone,
            )
            errors = self._introduced(checks, True)
            if errors:
                raise PipelineError(
                    f"the edited XML introduces errors: {'; '.join(e.details for e in errors)}"
                )
            update.update({"edited_xml": edited_xml, "checks": checks})
        updated = proposal.model_copy(update=update)
        self._replace(updated)
        self._log(
            event="decision",
            proposal=proposal_id,
            status=status,
            comment=comment,
            actor=actor,
        )
        self._refresh_stage()
        self._save()
        return updated

    def accept_all(self, actor: str = "user") -> list[str]:
        """Accept the proposals that are certain and clean; the others stay ``proposed``.

        Accepted: status ``proposed``, zone ``certain`` of kind ``content``, and no failing
        check that was introduced (a pre-existing problem of the document is not the change's
        fault). A proposal with a warning of its own (for instance an illustration flag) or an
        alternative with an introduced error is never accepted here.
        """
        self._need(*STAGES_FOR_REVIEW)
        accepted: list[str] = []
        for proposal in list(self.state.proposals):
            zone = self._zone_of(proposal)
            if proposal.status != "proposed" or zone is None:
                continue
            if zone.kind != "content" or zone.certainty != "certain":
                continue
            if self._introduced(proposal.checks):  # any error OR warning of its own
                continue
            self._replace(proposal.model_copy(update={"status": "accepted"}))
            self._log(
                event="decision",
                proposal=proposal.id,
                status="accepted",
                comment="accept-all",
                actor=actor,
            )
            accepted.append(proposal.id)
        self._refresh_stage()
        self._save()
        return accepted

    def auto_accept(self) -> list[str]:
        """``accept_all`` as actor ``auto``; only for a request created with ``auto_accept``."""
        if not self.request.auto_accept:
            raise PipelineError("auto-accept was not requested (tests and CLI option only)")
        return self.accept_all(actor="auto")

    def reject(
        self, proposal_id: str, reason: str | None = None, actor: str = "user"
    ) -> Proposal | None:
        """Reject a proposal and look for a code-generated alternative.

        Returns the new proposal (checked, appended to the state) or ``None`` when there is
        none: the event ``needs_manual_edit`` is then logged.
        """
        rejected = self.decide(proposal_id, "rejected", reason, actor=actor)
        zone = self._zone_of(rejected)
        if zone is None or zone.kind != "content":
            return None
        base = self._base_operation(rejected.operation_id)
        zones = [z for z in self.state.zones if z.operation_id == base.id]
        report = a5_preparer.prepare_report(
            base,
            zones,
            self.index,
            a5_preparer.Rejection(rejected, reason),
            max_alternatives=self._trace.max_alternatives,
        )
        if not report.proposals:
            self._log(event="needs_manual_edit", proposal=proposal_id)
            self._save()
            return None
        alternative, derived = report.proposals[0], report.operations[0]
        checks = a7_checker.check_proposal(
            alternative, self.index, self.state.baseline, operation=derived, zone=zone
        )
        alternative = alternative.model_copy(update={"checks": checks})
        self.state.operations.append(derived)
        self.state.proposals.append(alternative)
        self._log(event="alternative", proposal=proposal_id, alternative=alternative.id)
        self._refresh_stage()
        self._save()
        return alternative

    # --- policy and write --------------------

    def set_policy(self, policy: VersionPolicy) -> None:
        self.state.version_policy = policy
        self._log(event="policy", mode=policy.mode, per_doc=policy.per_doc)
        self._save()

    def write(self, today: datetime.date | None = None) -> WriteResult:
        """A11: write the accepted / edited proposals into ``<run>/out``; stage ``written``."""
        self._need(*STAGES_FOR_REVIEW)
        if self.state.version_policy is None:
            raise PipelineError("no versioning policy chosen")
        flags = {p.id for p in self.state.proposals if p.status == "proposed" and self._is_flag(p)}
        try:
            result = write(
                self.run_dir,
                self.index,
                self.state.proposals,
                self.state.version_policy,
                operations=self.state.operations,
                zones=self.state.zones,
                excluded=flags,  # flag-only proposals change nothing
                today=today,
            )
        except WriteRefused as exc:
            raise PipelineError(str(exc)) from exc
        self.state.stage = "written"
        self._log(
            event="written",
            files=[p.name for p in result.written],
            log=result.log,
            skipped=result.skipped,
        )
        self._save()
        return result


def start(
    request: RunRequest,
    workspace_path: Path | str,
    runs_dir: Path | str,
    clock: Callable[[], datetime.datetime] | None = None,
    token: str | None = None,
) -> Run:
    """``Run.start``: the new run (its ``state`` is the ``RunState``)."""
    return Run.start(request, workspace_path, runs_dir, clock, token)


def load(run_dir: Path | str) -> Run:
    """``Run.load``: resume a run from its folder."""
    return Run.load(run_dir)
