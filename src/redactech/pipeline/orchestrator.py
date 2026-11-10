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
the writer apply the variant. ``write`` also delivers ``report.json``, ``report.html``,
``questions.csv`` and ``decisions.jsonl`` (package ``redactech.report``) into the run folder.
``decisions_log`` also receives events (``skipped_readonly``, ``alternative``,
``needs_manual_edit``, ``written`` ...), each with a timestamp.
"""

from __future__ import annotations

import datetime
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, model_validator

from redactech.agents import (
    a1_indexer,
    a2_freetext,
    a2_mapping,
    a4_locator,
    a5_preparer,
    a7_checker,
)
from redactech.agents.a11_writer import WriteRefused, WriteResult, write
from redactech.config import load_config
from redactech.llm import LLMError, LLMProvider, get_provider
from redactech.models import CheckResult, Operation, Proposal, RunState, VersionPolicy, Zone
from redactech.report.build import build_report, question_entries
from redactech.report.export import export_decisions, export_questions, write_report
from redactech.s1000d import versioning
from redactech.s1000d.index import CorpusIndex, build_index, ref_key
from redactech.sources import workspace as wsmod

Mode = Literal["none", "in_work", "new_issue"]
STAGES_FOR_REVIEW = ("proposals_ready", "reviewed")
SUPERSEDED = "superseded by reopened proposal"
DECISIONS = ("accepted", "edited", "rejected", "pending_client")
STATE_FILE = "state.json"
LLM_LOG_FILE = "llm_calls.jsonl"
REQUEST_FILE = "request.json"


class PipelineError(RuntimeError):
    """A step was called at the wrong stage, or a decision is not allowed."""


class RunRequest(BaseModel):
    """What the writer asked for: a mapping file OR a form, and optionally a policy."""

    mapping: str | None = None
    form: dict[str, Any] | list[dict[str, Any]] | None = None  # one form or several
    free_text: str | None = None  # a request in French or English, read by the local model
    version_policy: Mode | None = None
    auto_accept: bool = False  # tests and the hidden CLI option only
    brex_swaps: list[str] = []  # BREX files swapped in (the UI's "change BREX")

    @model_validator(mode="after")
    def _one_source(self) -> RunRequest:
        given = [v for v in (self.mapping, self.form, self.free_text) if v is not None]
        if len(given) != 1:
            raise ValueError("give exactly one of mapping, form and free_text")
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
        self.delivery_files: list[Path] = []  # set by ``write``
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
        provider: LLMProvider | None = None,
    ) -> Run:
        """New run: index + baseline (A1), operations (A2); stops at ``ops_proposed``.

        A free-text request is read by the language model (``provider``, else the one of
        ``config.toml``); with no model configured it is refused with a ``PipelineError``. The
        questions of the interpretation are logged (``free_text_question``).
        """
        now = (clock or datetime.datetime.now)()
        run_id = f"{now:%Y%m%d-%H%M%S}-{token or secrets.token_hex(2)}"
        run_dir = Path(runs_dir) / run_id
        # the model calls are logged here while the run folder does not exist yet
        log_file = Path(runs_dir) / f"{run_id}.{LLM_LOG_FILE}"
        workspace_file = Path(workspace_path).resolve()
        workspace = wsmod.load_workspace(workspace_file)
        indexed = None
        questions: list[str] = []
        # read the request first: a bad request must not leave a half-created run
        if request.mapping is not None:
            operations = a2_mapping.mapping_operations(request.mapping)
        elif request.form is not None:
            operations = a2_mapping.from_form(request.form)
        else:  # free text: the prompt needs the index
            # the stored text is the stripped one, so the offsets of the quotes fit it
            request = request.model_copy(update={"free_text": (request.free_text or "").strip()})
            indexed = a1_indexer.run(workspace)
            found = cls._interpret(request.free_text or "", indexed[0], provider, log_file)
            operations, questions = found.operations, found.questions
        run_dir.mkdir(parents=True, exist_ok=False)
        if log_file.is_file():  # the log of the model calls moves into the run folder
            log_file.replace(run_dir / LLM_LOG_FILE)
        index, baseline = indexed or a1_indexer.run(workspace)
        for swapped in request.brex_swaps:  # chains resolved again, baseline recomputed
            baseline = a1_indexer.swap_brex(workspace, index, swapped)
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
        state.operations = operations
        state.stage = "ops_proposed"
        if request.version_policy is not None:
            suggestion = versioning.suggest_policy(operations)
            state.version_policy = suggestion.model_copy(update={"mode": request.version_policy})
        for question in questions:
            run._log(event="free_text_question", text=question)
        run._log(event="ops_proposed", operations=[o.id for o in operations])
        run._save()
        return run

    @staticmethod
    def _interpret(
        text: str, index: CorpusIndex, provider: LLMProvider | None, log_file: Path
    ) -> a2_freetext.Interpretation:
        """Read a free-text request with the model; every call is logged to ``log_file``.

        A provider made here is closed afterwards; one that is handed in is left open and gets
        its own log path back. A failed call keeps its log next to the runs
        (``<run id>.llm_calls.jsonl``): the refusal is explained, the attempt is not lost.
        """
        owned = provider is None
        model = None
        previous = None
        try:
            model = provider or get_provider(load_config())
            previous = model.log_path
            model.log_path = log_file
            return a2_freetext.interpret_full(text, index, model)
        except (LLMError, ValueError) as exc:
            raise PipelineError(f"free text needs the local model: {exc}") from exc
        finally:
            if model is not None:
                model.log_path = previous
                if owned:
                    model.close()

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
            for swapped in self.request.brex_swaps:
                a1_indexer.apply_swap(self._index, swapped)
        return self._index

    def free_text_questions(self) -> list[str]:
        """The questions raised when the free-text request was read (nothing was guessed)."""
        log = self.state.decisions_log
        return [str(e["text"]) for e in log if e.get("event") == "free_text_question"]

    def pending_ids(self) -> list[str]:
        """Proposals still to decide (flag-only illustration proposals do not count)."""
        return [
            p.id for p in self.state.proposals if p.status == "proposed" and not self._is_flag(p)
        ]

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

    def _locate(self, op: Operation) -> list[Zone] | None:
        """A4 for one operation; read-only occurrences and failures are logged, not zoned."""
        try:
            located = a4_locator.locate(op, self.index)
        except a4_locator.LocateError as exc:
            self._log(event="locate_error", operation=op.id, reason=str(exc))
            return None
        for skipped in located.skipped_readonly:
            self._log(
                event="skipped_readonly",
                operation=op.id,
                document=ref_key(skipped.ref),
                kind=skipped.kind,
                reason=skipped.reason,
            )
        return located.zones

    def propose_zones(self) -> None:
        """A4: where does each operation apply? Read-only occurrences are logged, not zoned."""
        self._need("ops_validated")
        zones: list[Zone] = []
        for op in self.state.operations:
            located = self._locate(op)
            if located is not None:
                zones.extend(located)
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

    def _taken_ids(self) -> frozenset[str]:
        ids = [p.id for p in self.state.proposals] + [o.id for o in self.state.operations]
        return frozenset(ids)

    def _is_flag(self, proposal: Proposal) -> bool:
        zone = self._zone_of(proposal)
        return zone is not None and zone.kind == "illustration"

    def is_flag(self, proposal: Proposal) -> bool:
        """Is this a flag-only proposal (a figure to check)? It changes nothing when written."""
        return self._is_flag(proposal)

    def counts(self) -> dict[str, int]:
        """Number of proposals per status (flag-only illustrations excluded)."""
        found: dict[str, int] = {}
        for proposal in self.state.proposals:
            if not self._is_flag(proposal):
                found[proposal.status] = found.get(proposal.status, 0) + 1
        return found

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
        if proposal.status not in ("proposed", "blocked_by_rule"):
            raise PipelineError(
                f"{proposal_id} is already decided ({proposal.status}): reopen it to change it"
            )
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

    def reopen(self, proposal_id: str, actor: str = "user") -> Proposal:
        """Take a decision back: the proposal returns to ``proposed`` (refused after the write).

        The open alternatives of the proposal (``replaces == proposal_id``) are rejected as
        superseded, so that a proposal and its replacement are never both live.
        """
        self._need(*STAGES_FOR_REVIEW)
        proposal = self._proposal(proposal_id)
        if proposal.status == "proposed":
            raise PipelineError(f"{proposal_id} is not decided yet")
        if proposal.status == "blocked_by_rule":
            raise PipelineError(f"{proposal_id} is blocked by a business rule: ask the customer")
        for other in list(self.state.proposals):
            if other.replaces == proposal_id and other.status == "proposed":
                self._replace(
                    other.model_copy(
                        update={"status": "rejected", "reviewer_comment": SUPERSEDED}
                    )
                )
                self._log(
                    event="decision",
                    proposal=other.id,
                    status="rejected",
                    comment=SUPERSEDED,
                    actor=actor,
                )
        reopened = proposal.model_copy(
            update={"status": "proposed", "reviewer_comment": None, "edited_xml": None}
        )
        self._replace(reopened)
        self._log(event="reopen", proposal=proposal_id, was=proposal.status, actor=actor)
        self._refresh_stage()
        self._save()
        return reopened

    def open_questions(self) -> list[str]:
        """The customer questions still open (proposals put on hold), one line each."""
        rows = [q for q in question_entries(self.state) if q.status == "pending_client"]
        return [f"{q.id} ({q.document}): {q.text}" for q in rows]

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
            taken=self._taken_ids(),
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
        if alternative.id in self._taken_ids():  # never a duplicate id in the run
            raise PipelineError(f"{alternative.id} already exists in the run")
        self.state.operations.append(derived)
        self.state.proposals.append(alternative)
        self._log(event="alternative", proposal=proposal_id, alternative=alternative.id)
        self._refresh_stage()
        self._save()
        return alternative

    # --- operations added during the review (the chat assistant) ---------------------------

    def add_operations(self, operations: list[Operation]) -> tuple[list[Operation], list[Proposal]]:
        """Add operations to a run under review: same locator, preparer and checks as the first.

        The operations get the next ids (``op-NNNN``); their proposals need decisions like any
        other (nothing is accepted here) and the stage goes back to ``proposals_ready`` when one
        is undecided. Returns the operations added and their proposals.
        """
        self._need(*STAGES_FOR_REVIEW)
        numbers = [
            int(o.id[3:]) for o in self.state.operations if o.id[3:].isdigit() and o.id[:3] == "op-"
        ]
        number = max(numbers, default=0)
        added: list[Operation] = []
        proposals: list[Proposal] = []
        for operation in operations:
            number += 1
            op = operation.model_copy(update={"id": f"op-{number:04d}"})
            zones = self._locate(op)
            if zones is None:
                continue
            self.state.zones.extend(zones)
            checked = a5_preparer.prepare_checked(
                op,
                zones,
                self.index,
                self.state.baseline,
                max_rule_retries=self._trace.max_rule_retries,
            )
            for error in checked.errors:
                self._log(event="prepare_error", operation=op.id, reason=error)
            self.state.operations.extend(checked.all_operations)
            self.state.proposals.extend(checked.proposals)
            added.append(op)
            proposals.extend(checked.proposals)
        if added:
            self._log(event="operations_added", operations=[o.id for o in added])
            self._refresh_stage()
        self._save()
        return added, proposals

    def note_question(self, text: str) -> None:
        """Record a question for the customer that came out of a free-text request."""
        self._log(event="free_text_question", text=text)
        self._save()

    # --- policy and write --------------------

    def set_policy(self, policy: VersionPolicy) -> None:
        self.state.version_policy = policy
        self._log(event="policy", mode=policy.mode, per_doc=policy.per_doc)
        self._save()

    def write(
        self, today: datetime.date | None = None, policy: VersionPolicy | None = None
    ) -> WriteResult:
        """A11: write the accepted / edited proposals into ``<run>/out``; stage ``written``.

        ``policy`` (optional) is used for this write and saved only if the write succeeds.
        """
        self._need(*STAGES_FOR_REVIEW)
        chosen = policy or self.state.version_policy
        if chosen is None:
            raise PipelineError("no versioning policy chosen")
        flags = {p.id for p in self.state.proposals if p.status == "proposed" and self._is_flag(p)}
        try:
            result = write(
                self.run_dir,
                self.index,
                self.state.proposals,
                chosen,
                operations=self.state.operations,
                zones=self.state.zones,
                excluded=flags,  # flag-only proposals change nothing
                today=today,
                trace_config=self._trace,
            )
        except WriteRefused as exc:
            raise PipelineError(str(exc)) from exc
        if policy is not None:
            self.set_policy(policy)
        result.open_questions = self.open_questions()
        self.state.stage = "written"
        self._log(
            event="written",
            files=[p.name for p in result.written],
            log=result.log,
            skipped=result.skipped,
        )
        self._save()
        self.delivery_files = self._deliver(result)
        return result

    def _deliver(self, result: WriteResult) -> list[Path]:
        """Write the delivery files next to the state: report, questions, decisions."""
        report = build_report(self.state, self.index, result)
        json_path, html_path = write_report(self.run_dir, report)
        questions = export_questions(self.state, self.run_dir / "questions.csv")
        export_questions(self.state, self.run_dir / "questions.xlsx")  # for the UI download
        decisions = export_decisions(self.state, self.run_dir / "decisions.jsonl")
        return [json_path, html_path, questions, decisions]


def start(
    request: RunRequest,
    workspace_path: Path | str,
    runs_dir: Path | str,
    clock: Callable[[], datetime.datetime] | None = None,
    token: str | None = None,
    provider: LLMProvider | None = None,
) -> Run:
    """``Run.start``: the new run (its ``state`` is the ``RunState``)."""
    return Run.start(request, workspace_path, runs_dir, clock, token, provider)


def load(run_dir: Path | str) -> Run:
    """``Run.load``: resume a run from its folder."""
    return Run.load(run_dir)
