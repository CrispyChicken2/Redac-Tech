"""A5 - change preparer: turns an operation and its zones into reviewable proposals.

Each content zone is applied on an in-memory COPY of its data module (nothing is written), and
the changed element is serialised before and after. Illustration zones give a flag-only
proposal (``before_xml == after_xml``) carrying an ``illustration`` warning "to check".
``prepare_checked`` adds the checker (A7) and the BREX retry / ``blocked_by_rule`` logic; marks,
versioning and writing belong to the writer.

When the writer rejects a proposal, ``prepare(..., rejection=...)`` offers a code-generated
ALTERNATIVE when one exists, else nothing ("needs manual edit"):

* ``replace_part`` / ``replace_text``: replace only the first, then only the last mention in
  the element (useful when a paragraph mentions the part twice);
* ``insert_step`` / ``move_step``: the neighbouring position (after the next step, before the
  previous step) and the opposite side of the reference step.

Candidates are tried on a copy and kept only if they differ from the rejected proposal and from
each other. Successive rejections walk the list; at most ``max_alternatives`` alternatives are
offered per proposal (``config.toml``: ``trace.max_alternatives``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redactech.agents import a7_checker
from redactech.models import CheckResult, Operation, Proposal, SourceRef, Zone
from redactech.s1000d import io as xio
from redactech.s1000d import ops
from redactech.s1000d.index import CorpusIndex, ref_key
from redactech.s1000d.ops._common import OpError, OpResult, by_id, target_of, xml_of

DEFAULT_MAX_ALTERNATIVES = 3
STEP = "proceduralStep"


@dataclass(frozen=True)
class Rejection:
    """A rejected proposal and the writer's reason, if any."""

    proposal: Proposal
    feedback: str | None = None


@dataclass
class PrepareReport:
    proposals: list[Proposal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # zones the operation could not be applied to
    # Operations derived for alternatives (own id and parameters): an alternative proposal
    # points at one of them, so the checker and the writer apply the variant, not the original.
    operations: list[Operation] = field(default_factory=list)


def _original(index: CorpusIndex, ref: SourceRef, cache: dict[str, Any]) -> Any:
    key = ref_key(ref)
    if key not in cache:
        doc = index.docs.get(key)
        if doc is None:
            raise OpError(f"unknown document {key}")
        cache[key] = xio.load(doc.path)
    return cache[key]


def _merged(params: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = {**params, **override}
    return {k: v for k, v in merged.items() if v is not None}


def _apply(
    index: CorpusIndex, op: Operation, zone: Zone, params: dict[str, Any], cache: dict[str, Any]
) -> OpResult:
    tree = ops.copy_tree(_original(index, zone.ref, cache).tree)
    return ops.apply(tree, op.kind, zone, params)


def _flag_proposal(
    index: CorpusIndex, op: Operation, zone: Zone, proposal_id: str, cache: dict[str, Any]
) -> Proposal:
    tree = ops.copy_tree(_original(index, zone.ref, cache).tree)
    xml = xml_of(target_of(tree, zone))
    warning = CheckResult(
        name="illustration",
        ok=False,
        severity="warning",
        details=f"to check: {zone.reason}",
        ref=zone.ref,
        xpath=zone.xpath or None,
    )
    return Proposal(
        id=proposal_id,
        operation_id=op.id,
        zone_id=zone.id,
        ref=zone.ref,
        before_xml=xml,
        after_xml=xml,
        change_type="modify",
        checks=[warning],
    )


def _proposal(op: Operation, zone: Zone, proposal_id: str, result: OpResult) -> Proposal:
    return Proposal(
        id=proposal_id,
        operation_id=op.id,
        zone_id=zone.id,
        ref=zone.ref,
        before_xml=result.before_xml,
        after_xml=result.after_xml,
        change_type=result.change_type,
    )


def _neighbour_ids(tree: Any, step_id: str) -> tuple[str | None, str | None]:
    """Ids of the steps just before and just after ``step_id`` (None if absent)."""
    try:
        step = by_id(tree, step_id, STEP)
    except OpError:
        return None, None
    previous, following = step.getprevious(), step.getnext()

    def step_id_of(node: Any) -> str | None:
        return node.get("id") if node is not None and node.tag == STEP else None

    return step_id_of(previous), step_id_of(following)


def _candidates(op: Operation, zone: Zone, tree: Any) -> list[dict[str, Any]]:
    """Parameter overrides to try for an alternative, most useful first."""
    params = op.params
    if op.kind in ("replace_part", "replace_text"):
        return [] if "occurrence" in params else [{"occurrence": 1}, {"occurrence": -1}]
    if op.kind in ("insert_step", "move_step"):
        after_id, before_id = params.get("after_id"), params.get("before_id")
        if after_id:
            _, following = _neighbour_ids(tree, after_id)
            nearby = [{"after_id": following}] if following else []
            return [*nearby, {"after_id": None, "before_id": after_id}]
        if before_id:
            previous, _ = _neighbour_ids(tree, before_id)
            nearby = [{"before_id": previous}] if previous else []
            return [*nearby, {"before_id": None, "after_id": before_id}]
    return []


def _alternative(
    index: CorpusIndex,
    op: Operation,
    zone: Zone,
    rejection: Rejection,
    cache: dict[str, Any],
) -> tuple[Proposal, Operation] | None:
    rejected = rejection.proposal
    original_tree = _original(index, zone.ref, cache).tree
    try:
        base = _apply(index, op, zone, op.params, cache)
    except OpError:
        return None
    seen = {(base.element_xpath, base.after_xml)}
    found: list[tuple[OpResult, dict[str, Any]]] = []
    for override in _candidates(op, zone, original_tree):
        merged = _merged(op.params, override)
        try:
            result = _apply(index, op, zone, merged, cache)
        except OpError:
            continue
        key = (result.element_xpath, result.after_xml)
        if key not in seen:
            seen.add(key)
            found.append((result, merged))
    position = rejected.attempt - 1
    if position >= len(found):
        return None
    attempt = rejected.attempt + 1
    feedback = [*rejected.rejection_feedback]
    if rejection.feedback:
        feedback.append(rejection.feedback)
    result, params = found[position]
    derived = op.model_copy(update={"id": f"{op.id}-a{attempt}-{zone.id}", "params": params})
    proposal = _proposal(derived, zone, f"{rejected.id}-a{attempt}", result)
    proposal = proposal.model_copy(
        update={"attempt": attempt, "replaces": rejected.id, "rejection_feedback": feedback}
    )
    return proposal, derived


def prepare_report(
    op: Operation,
    zones: list[Zone],
    index: CorpusIndex,
    rejection: Rejection | None = None,
    max_alternatives: int = DEFAULT_MAX_ALTERNATIVES,
) -> PrepareReport:
    """Proposals for ``zones`` (or the alternative to ``rejection``) and the zones that failed."""
    report = PrepareReport()
    cache: dict[str, Any] = {}
    if rejection is not None:
        rejected = rejection.proposal
        zone = next((z for z in zones if z.id == rejected.zone_id), None)
        if zone is None or zone.kind != "content" or rejected.attempt > max_alternatives:
            return report
        try:
            alternative = _alternative(index, op, zone, rejection, cache)
        except OpError as exc:
            report.errors.append(f"{zone.id}: {exc}")
            return report
        if alternative is not None:
            report.proposals.append(alternative[0])
            report.operations.append(alternative[1])
        return report
    for number, zone in enumerate(zones, 1):
        proposal_id = f"prop-{op.id}-{number}"
        try:
            if zone.kind == "illustration":
                report.proposals.append(_flag_proposal(index, op, zone, proposal_id, cache))
            else:
                result = _apply(index, op, zone, op.params, cache)
                report.proposals.append(_proposal(op, zone, proposal_id, result))
        except OpError as exc:
            report.errors.append(f"{zone.id}: {exc}")
    return report


def prepare(
    op: Operation,
    zones: list[Zone],
    index: CorpusIndex,
    rejection: Rejection | None = None,
    max_alternatives: int = DEFAULT_MAX_ALTERNATIVES,
) -> list[Proposal]:
    """``prepare_report(...).proposals``: the proposals only (``[]`` = "needs manual edit")."""
    return prepare_report(op, zones, index, rejection, max_alternatives).proposals


# --- checked preparation: BREX failures, retries and blocked_by_rule ----------


DEFAULT_MAX_RULE_RETRIES = 2


@dataclass
class CheckedResult:
    """Checked proposals, the operation (its ``questions`` may have grown) and the failures."""

    proposals: list[Proposal] = field(default_factory=list)
    operation: Operation | None = None
    extra_operations: list[Operation] = field(default_factory=list)  # derived for alternatives
    errors: list[str] = field(default_factory=list)

    @property
    def all_operations(self) -> list[Operation]:
        """The operation and the derived ones: what the writer needs to apply the proposals."""
        return [self.operation, *self.extra_operations] if self.operation else []


def _introduced_brex(checks: list[CheckResult]) -> list[CheckResult]:
    return [
        c
        for c in checks
        if c.name == "brex" and not c.ok and c.severity == "error" and c.origin == "introduced"
    ]


def _rule_ids(checks: list[CheckResult]) -> set[str]:
    return {str((c.rule or {}).get("id", "")) for c in _introduced_brex(checks)}


def customer_question(op: Operation, rule: dict[str, Any]) -> str:
    """The pre-filled question sent to the customer when a business rule blocks a request."""
    quote = op.source[0].quote if op.source else op.rationale
    message = str(rule.get("message") or rule.get("xpath") or "").rstrip(". ")
    return (
        f"The request '{quote}' conflicts with business rule {rule.get('id')}: {message}. "
        "How should we proceed?"
    )


def prepare_checked(
    op: Operation,
    zones: list[Zone],
    index: CorpusIndex,
    baseline: list[CheckResult],
    max_rule_retries: int = DEFAULT_MAX_RULE_RETRIES,
) -> CheckedResult:
    """Proposals with their checks; BREX failures caused by the change are retried, then blocked.

    For each content zone the proposal is checked by A7. If it ``introduces`` a BREX error, the
    code alternatives of ``prepare`` (other form or position) are tried, at most
    ``max_rule_retries`` times, so at most ``1 + max_rule_retries`` attempts per zone (never a
    loop). The first alternative without introduced BREX error replaces the proposal
    (``replaces``, ``attempt``). If none is found and every attempt hits the same rule (the
    failure is inherent to the request, also when no alternative exists), the proposal gets
    the status ``blocked_by_rule`` (attempts counted in ``attempt``, rule kept in its checks)
    and the operation receives a pre-filled customer question. If the attempts hit different
    rules the original proposal is kept as ``proposed`` with its errors.
    """
    report = prepare_report(op, zones, index)
    result = CheckedResult(operation=op, errors=list(report.errors))
    by_zone = {z.id: z for z in zones}
    cache: dict[str, Any] = {}
    questions = list(op.questions)
    for proposal in report.proposals:
        zone = by_zone[proposal.zone_id]
        if zone.kind != "content":
            result.proposals.append(proposal)  # a flag-only proposal keeps its warning
            continue
        checks = a7_checker.check_proposal(proposal, index, baseline, operation=op, zone=zone)
        current = proposal.model_copy(update={"checks": checks})
        if not _introduced_brex(checks):
            result.proposals.append(current)
            continue
        attempts = [current]
        passing: tuple[Proposal, Operation] | None = None
        for _ in range(max_rule_retries):
            try:
                alternative = _alternative(index, op, zone, Rejection(attempts[-1]), cache)
            except OpError:
                alternative = None
            if alternative is None:
                break
            variant, derived = alternative
            alt_checks = a7_checker.check_proposal(
                variant, index, baseline, operation=derived, zone=zone
            )
            variant = variant.model_copy(update={"checks": alt_checks})
            attempts.append(variant)
            if not _introduced_brex(alt_checks):
                passing = (variant, derived)
                break
        if passing is not None:
            result.proposals.append(passing[0])
            result.extra_operations.append(passing[1])
            continue
        common = set.intersection(*(_rule_ids(a.checks) for a in attempts))
        if not common:
            result.proposals.append(current)  # different rules each time: left to the writer
            continue
        rule = next(
            dict(c.rule or {})
            for c in _introduced_brex(current.checks)
            if str((c.rule or {}).get("id", "")) in common
        )
        notes = [
            f"attempt {n}: {', '.join(sorted(_rule_ids(a.checks)))}"
            for n, a in enumerate(attempts[1:], 2)
        ]
        result.proposals.append(
            current.model_copy(
                update={
                    "status": "blocked_by_rule",
                    "attempt": len(attempts),
                    "rejection_feedback": [*current.rejection_feedback, *notes],
                }
            )
        )
        question = customer_question(op, rule)
        if question not in questions:
            questions.append(question)
    result.operation = op.model_copy(update={"questions": questions})
    return result
