"""Delivery report: what was asked, decided, written, checked and left open.

``build_report(state, index, write_result)`` turns a run into a ``Report`` (pydantic, so it
serialises to ``report.json`` as is). Per data module it lists the old and new file names, the
policy applied, the changes with their status and reviewer comment, and the checks split into
``pre_existing`` (already in the document before the change) and ``introduced``. Blocked
requests (rule and question), figures to check and open questions have their own lists, and
``counts`` totals the statuses. Nothing here reads a data module: names come from the index and
the write log, excerpts from the proposals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from redactech.agents import a7_checker
from redactech.models import (
    CheckResult,
    Operation,
    Proposal,
    RunState,
    SourceRef,
    VersionPolicy,
    Zone,
)
from redactech.s1000d import io as xio
from redactech.s1000d.index import CorpusIndex, ref_key

EXCERPT = 600  # characters kept of a before / after XML excerpt


class ChangeEntry(BaseModel):
    proposal_id: str
    operation_id: str
    operation: str  # the operation kind
    change_type: str
    status: str
    before: str = ""
    after: str = ""
    comment: str | None = None
    attempt: int = 1
    written: bool = False  # accepted / edited and part of the written document


class CheckEntry(BaseModel):
    name: str
    severity: str
    details: str
    origin: str
    xpath: str | None = None
    rule: dict[str, Any] | None = None


class DocumentReport(BaseModel):
    document: str  # reference key of the source document
    old_name: str
    new_name: str | None = None  # None: no new file was written for it
    policy: str | None = None  # versioning mode applied to this document
    changes: list[ChangeEntry] = Field(default_factory=list)
    pre_existing: list[CheckEntry] = Field(default_factory=list)
    introduced: list[CheckEntry] = Field(default_factory=list)


class BlockedEntry(BaseModel):
    proposal_id: str
    operation_id: str
    document: str
    attempts: int
    rule: dict[str, Any] | None = None
    question: str | None = None


class IllustrationEntry(BaseModel):
    proposal_id: str
    operation_id: str
    document: str
    figure_id: str | None = None
    reason: str
    status: str


class QuestionEntry(BaseModel):
    id: str  # proposal id, or operation id for a question not tied to a proposal
    document: str = ""
    element: str = ""
    text: str
    status: str
    rule: str = ""


class OutputCheck(BaseModel):
    """The A7 check of one delivered file, as ``redactech check`` does (REQ-11)."""

    file: str
    document: str  # reference key of the source document
    introduced_errors: int = 0
    introduced_warnings: int = 0
    pre_existing: int = 0
    error: str | None = None  # the file could not be checked


class Counts(BaseModel):
    accepted: int = 0
    edited: int = 0
    rejected: int = 0
    pending_client: int = 0
    blocked: int = 0
    proposed: int = 0  # still undecided (flag-only illustrations excluded)
    pre_existing: int = 0
    introduced: int = 0
    delivered_introduced_errors: int | None = None  # None: delivered files not checked


class Report(BaseModel):
    run_id: str
    workspace: str
    version_policy: VersionPolicy | None = None
    documents: list[DocumentReport] = Field(default_factory=list)
    blocked: list[BlockedEntry] = Field(default_factory=list)
    illustrations: list[IllustrationEntry] = Field(default_factory=list)
    questions: list[QuestionEntry] = Field(default_factory=list)
    skipped: list[dict[str, str]] = Field(default_factory=list)  # read-only documents
    outputs: list[OutputCheck] = Field(default_factory=list)  # check of each delivered file
    counts: Counts = Field(default_factory=Counts)


# --- helpers -------------------------------------------------------------------------------


def excerpt(xml: str) -> str:
    """The first ``EXCERPT`` characters of an XML string, marked when cut."""
    text = (xml or "").strip()
    return text if len(text) <= EXCERPT else text[:EXCERPT] + "…"


def rule_text(rule: dict[str, Any] | None) -> str:
    """``id: message`` of a BREX rule dict (empty when there is no rule)."""
    if not rule:
        return ""
    rule_id, message = str(rule.get("id", "")), str(rule.get("message") or rule.get("xpath") or "")
    return f"{rule_id}: {message}".strip(": ")


def _checks(proposals: list[Proposal], origin: str) -> list[CheckEntry]:
    """Failing checks of the given origin, without duplicates, in order."""
    seen: set[tuple] = set()
    found: list[CheckEntry] = []
    for proposal in proposals:
        for check in proposal.checks:
            if check.ok or check.origin != origin or check.name == "illustration":
                continue
            key = (check.name, check.details, check.xpath, str((check.rule or {}).get("id", "")))
            if key not in seen:
                seen.add(key)
                found.append(_entry(check))
    return found


def _entry(check: CheckResult) -> CheckEntry:
    return CheckEntry(
        name=check.name,
        severity=check.severity,
        details=check.details,
        origin=check.origin,
        xpath=check.xpath,
        rule=check.rule,
    )


def _element_of(zone: Zone | None) -> str:
    return (zone.element_id or zone.xpath) if zone is not None else ""


def _question_for(proposal: Proposal, operations: dict[str, Operation]) -> str | None:
    """The pre-filled question of a blocked proposal: the one that names its rule."""
    operation = operations.get(proposal.operation_id)
    if operation is None:
        return None
    rule_id = next((str(c.rule.get("id", "")) for c in proposal.checks if c.rule), "")
    for question in operation.questions:
        if rule_id and rule_id in question:
            return question
    return operation.questions[0] if operation.questions else None


def question_entries(state: RunState) -> list[QuestionEntry]:
    """Open questions: customer questions of pending proposals, blocked requests, operations."""
    zones = {z.id: z for z in state.zones}
    operations = {o.id: o for o in state.operations}
    rows: list[QuestionEntry] = []
    used: set[tuple[str, str]] = set()
    for proposal in state.proposals:
        zone = zones.get(proposal.zone_id)
        if proposal.status == "pending_client":
            rows.append(
                QuestionEntry(
                    id=proposal.id,
                    document=ref_key(proposal.ref),
                    element=_element_of(zone),
                    text=proposal.reviewer_comment or "",
                    status="pending_client",
                )
            )
        elif proposal.status == "blocked_by_rule":
            question = _question_for(proposal, operations)
            rule = next((c.rule for c in proposal.checks if c.rule and not c.ok), None)
            if question:
                used.add((proposal.operation_id, question))
            rows.append(
                QuestionEntry(
                    id=proposal.id,
                    document=ref_key(proposal.ref),
                    element=_element_of(zone),
                    text=question or "",
                    status="blocked_by_rule",
                    rule=rule_text(rule),
                )
            )
    for operation in state.operations:
        for question in operation.questions:
            if (operation.id, question) not in used:
                document = ref_key(operation.target.ref) if operation.target.ref else ""
                element = operation.target.element_id or operation.target.xpath or ""
                rows.append(
                    QuestionEntry(
                        id=operation.id,
                        document=document,
                        element=element,
                        text=question,
                        status="open",
                    )
                )
    return rows


# --- the report ----------------------------------------------------------------------------


def build_report(state: RunState, index: CorpusIndex, write_result: Any = None) -> Report:
    """The report of a run; ``write_result`` is the ``WriteResult`` of the write (or None)."""
    zones = {z.id: z for z in state.zones}
    operations = {o.id: o for o in state.operations}
    log = {entry["doc"]: entry for entry in getattr(write_result, "log", []) or []}
    skipped = list(getattr(write_result, "skipped", []) or [])

    flags = [p for p in state.proposals if _is_flag(p, zones)]
    content = [p for p in state.proposals if p.id not in {f.id for f in flags}]
    by_doc: dict[str, list[Proposal]] = {}
    for proposal in content:
        if proposal.status != "blocked_by_rule":
            by_doc.setdefault(ref_key(proposal.ref), []).append(proposal)
    for key in log:
        by_doc.setdefault(key, [])

    documents = []
    for key, proposals in by_doc.items():
        entry = log.get(key)
        doc = index.docs.get(key)
        old_name = Path(doc.path).name if doc is not None else key
        written_ids = set(entry["proposals"]) if entry else set()
        documents.append(
            DocumentReport(
                document=key,
                old_name=old_name,
                new_name=entry["new_name"] if entry else None,
                policy=entry["policy"] if entry else None,
                changes=[_change(p, operations, p.id in written_ids) for p in proposals],
                pre_existing=_checks(proposals, "pre_existing"),
                introduced=_checks(proposals, "introduced"),
            )
        )

    blocked = [
        BlockedEntry(
            proposal_id=p.id,
            operation_id=p.operation_id,
            document=ref_key(p.ref),
            attempts=p.attempt,
            rule=next((c.rule for c in p.checks if c.rule and not c.ok), None),
            question=_question_for(p, operations),
        )
        for p in content
        if p.status == "blocked_by_rule"
    ]
    illustrations = [
        IllustrationEntry(
            proposal_id=p.id,
            operation_id=p.operation_id,
            document=ref_key(p.ref),
            figure_id=zones[p.zone_id].element_id if p.zone_id in zones else None,
            reason=zones[p.zone_id].reason if p.zone_id in zones else "",
            status=p.status,
        )
        for p in flags
    ]

    counts = Counts(
        accepted=sum(p.status == "accepted" for p in content),
        edited=sum(p.status == "edited" for p in content),
        rejected=sum(p.status == "rejected" for p in content),
        pending_client=sum(p.status == "pending_client" for p in content),
        blocked=len(blocked),
        proposed=sum(p.status == "proposed" for p in content),
        pre_existing=sum(len(d.pre_existing) for d in documents),
        introduced=sum(len(d.introduced) for d in documents),
    )
    outputs = check_outputs(state, index, write_result)
    if getattr(write_result, "written", None):
        counts.delivered_introduced_errors = sum(o.introduced_errors for o in outputs)
    return Report(
        run_id=state.run_id,
        workspace=state.workspace,
        version_policy=state.version_policy,
        documents=documents,
        blocked=blocked,
        illustrations=illustrations,
        questions=question_entries(state),
        skipped=skipped,
        counts=counts,
        outputs=outputs,
    )


def check_outputs(state: RunState, index: CorpusIndex, write_result: Any) -> list[OutputCheck]:
    """Check every delivered file (A7 ``check_doc``): introduced vs pre-existing counts."""
    written = list(getattr(write_result, "written", []) or [])
    originals = {
        entry["new_name"]: entry["doc"] for entry in getattr(write_result, "log", []) or []
    }
    results: list[OutputCheck] = []
    for path in written:
        key = originals.get(Path(path).name, "")
        doc = index.docs.get(key)
        item = OutputCheck(file=Path(path).name, document=key)
        if doc is None:
            item.error = "not produced from a known document"
        else:
            try:
                ref = SourceRef(source_id=doc.ref.source_id, doc_key=Path(path).stem)
                failures = a7_checker.check_doc(
                    xio.load(path), index, state.baseline, original=doc.ref, ref=ref
                )
            except Exception as exc:  # a file that cannot be read or checked is reported
                item.error = str(exc)
            else:
                introduced = [f for f in failures if f.origin == "introduced"]
                item.introduced_errors = sum(1 for f in introduced if f.severity == "error")
                item.introduced_warnings = len(introduced) - item.introduced_errors
                item.pre_existing = len(failures) - len(introduced)
        results.append(item)
    return results


def _is_flag(proposal: Proposal, zones: dict[str, Zone]) -> bool:
    zone = zones.get(proposal.zone_id)
    return zone is not None and zone.kind == "illustration"


def _change(proposal: Proposal, operations: dict[str, Operation], written: bool) -> ChangeEntry:
    operation = operations.get(proposal.operation_id)
    after = proposal.edited_xml if proposal.status == "edited" and proposal.edited_xml else None
    return ChangeEntry(
        proposal_id=proposal.id,
        operation_id=proposal.operation_id,
        operation=operation.kind if operation is not None else "",
        change_type=proposal.change_type,
        status=proposal.status,
        before=excerpt(proposal.before_xml),
        after=excerpt(after if after is not None else proposal.after_xml),
        comment=proposal.reviewer_comment,
        attempt=proposal.attempt,
        written=written,
    )
