"""A11 - writer: turns DECIDED proposals into new data modules in ``<run_dir>/out``.

* Only proposals with status ``accepted`` or ``edited`` are written (``edited`` uses the
  ``edited_xml`` of the writer in place of the generated element). ``rejected``,
  ``pending_client`` and ``blocked_by_rule`` are never written.
* A proposal still ``proposed`` blocks everything (no change without a decision) unless its
  id is listed in ``excluded``. Nothing is written when the request is refused: all documents
  are prepared in memory first.
* The source files are never modified: each data module is loaded, the operations are
  re-applied on that private copy (no string splicing), the changed elements are marked, a
  reason for update is added from the operation rationale, the versioning policy is applied
  and the result is saved under its new file name in ``out``.
* Update files, BREX, publication modules, delivery notes and graphics are never written.
* To survive several operations on one document, each target element is tagged with a
  temporary attribute before the operations run (earlier insertions would shift positional
  xpaths); the attribute is removed before saving.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from redactech.config import TraceConfig
from redactech.models import Operation, Proposal, VersionPolicy, Zone
from redactech.s1000d import io as xio
from redactech.s1000d import ops, trace, versioning
from redactech.s1000d.index import CorpusIndex, ref_key
from redactech.s1000d.ops._common import OpError, OpResult

APPLIED = ("accepted", "edited")
TEMP_ATTRIBUTE = "rt-target"


class WriteRefused(Exception):
    """The write is refused (undecided proposals, unknown zone...); nothing was written."""


@dataclass
class WriteResult:
    written: list[Path] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)  # set by the Run (customer on hold)

    @property
    def warning(self) -> str:
        """A warning about the open customer questions ("" when there is none)."""
        return open_questions_warning(self.open_questions)


def open_questions_warning(questions: list[str]) -> str:
    n = len(questions)
    return f"{n} questions client ouvertes (en attente)" if n else ""


def _policy_mode(policy: VersionPolicy, key: str, doc_key: str) -> str:
    return policy.per_doc.get(key) or policy.per_doc.get(doc_key) or policy.mode


def _replace_with_edit(element: Any, edited_xml: str) -> Any:
    try:
        new = etree.fromstring(edited_xml.encode("utf-8"), xio.make_parser())
    except etree.LxmlError as exc:
        raise WriteRefused(f"edited XML is not well-formed: {exc}") from exc
    tail = element.tail
    element.getparent().replace(element, new)
    new.tail = tail
    return new


def _tag_targets(tree: Any, group: list[Proposal], zones: dict[str, Zone]) -> dict[str, Zone]:
    """Give each positional zone a stable temporary handle; returns the zones to use."""
    resolved: dict[str, Zone] = {}
    for number, proposal in enumerate(group, 1):
        zone = zones[proposal.zone_id]
        if zone.xpath:
            try:
                found = xio.xpath(tree, zone.xpath)
            except etree.LxmlError as exc:
                raise WriteRefused(f"invalid zone xpath {zone.xpath!r}: {exc}") from exc
            if not isinstance(found, list) or not found:
                raise WriteRefused(f"zone {zone.id}: target not found in the data module")
            handle = found[0].get(TEMP_ATTRIBUTE) or str(number)  # reuse a shared target's handle
            found[0].set(TEMP_ATTRIBUTE, handle)
            zone = zone.model_copy(update={"xpath": f"//*[@{TEMP_ATTRIBUTE}='{handle}']"})
        resolved[proposal.id] = zone
    return resolved


def _strip_handles(tree: Any) -> None:
    for element in xio.root_of(tree).iter():
        if isinstance(element.tag, str) and TEMP_ATTRIBUTE in element.attrib:
            del element.attrib[TEMP_ATTRIBUTE]


def _prepare_document(
    key: str,
    doc: Any,
    group: list[Proposal],
    index_ops: dict[str, Operation],
    zones: dict[str, Zone],
    policy: VersionPolicy,
    today: datetime.date | None,
    config: TraceConfig,
) -> tuple[Any, str, dict[str, Any]]:
    """The modified document, its new file name and its log entry."""
    xdoc = xio.load(doc.path)
    mode = _policy_mode(policy, key, doc.ref.doc_key)
    # Zone xpaths are positional on the ORIGINAL file: resolve them (tag the targets) BEFORE the
    # consolidation removes elements and shifts the positions.
    resolved = _tag_targets(xdoc.tree, group, zones)
    if mode == "new_issue" and config.consolidate_on_new_issue:
        trace.consolidate(xdoc)  # first: this cycle's marks are written afterwards
        for proposal in group:
            zone = resolved[proposal.id]
            if zone.xpath.startswith("//*[@") and not xio.xpath(xdoc.tree, zone.xpath):
                raise WriteRefused(
                    f"{proposal.id}: its target was marked for deletion in a previous cycle "
                    "and disappears when the new issue consolidates"
                )
    write_marks = mode != "none" or config.marks_when_none
    marks: list[dict[str, str]] = []
    for proposal in group:
        operation = index_ops[proposal.operation_id]
        try:
            result: OpResult = ops.apply(
                xdoc.tree, operation.kind, resolved[proposal.id], operation.params
            )
            target = xio.xpath(xdoc.tree, result.element_xpath)[0]
            edited = proposal.status == "edited" and proposal.edited_xml
            if edited and result.change_type != "delete":
                target = _replace_with_edit(target, proposal.edited_xml)
        except OpError as exc:
            raise WriteRefused(f"{proposal.id}: {exc}") from exc
        if write_marks:
            text = operation.rationale.strip() or f"{operation.kind} requested"
            rfu = trace.ensure_reason(xdoc, text)
            marked = trace.mark(target, result.change_type, rfu)
            marks.append(
                {
                    "proposal": proposal.id,
                    "change_type": result.change_type,
                    "reason": rfu,
                    "element": marked.getroottree().getpath(marked),
                }
            )
    _strip_handles(xdoc.tree)
    new_name = versioning.apply_policy(xdoc, mode, today, config, consolidate=False)
    entry = {
        "doc": key,
        "old_name": Path(doc.path).name,
        "new_name": new_name,
        "policy": mode,
        "proposals": [p.id for p in group],
        "marks": marks,
    }
    return xdoc, new_name, entry


def apply_to_copy(
    index: CorpusIndex, proposal: Proposal, operation: Operation, zone: Zone
) -> Any:
    """The data module of ``proposal`` with the change and its trace marks, in memory only.

    This is what ``write`` would save (policy ``none``, marks on), used by the checker to test
    a proposal before any decision. Raises ``WriteRefused`` if it cannot be applied.
    """
    key = ref_key(proposal.ref)
    doc = index.docs.get(key)
    if doc is None or doc.role != "dm" or not doc.writable:
        raise WriteRefused(f"{key} is not a writable data module")
    policy = VersionPolicy(mode="none", suggested="none")
    try:
        xdoc, _name, _entry = _prepare_document(
            key, doc, [proposal], {operation.id: operation}, {zone.id: zone}, policy, None,
            TraceConfig(),
        )
    except (OpError, trace.TraceError, versioning.VersioningError) as exc:
        raise WriteRefused(str(exc)) from exc
    return xdoc


def write(
    run_dir: Path | str,
    index: CorpusIndex,
    proposals: list[Proposal],
    policy: VersionPolicy,
    *,
    operations: list[Operation],
    zones: list[Zone],
    decided: bool = True,
    excluded: set[str] | frozenset[str] | tuple[str, ...] = (),
    today: datetime.date | None = None,
    trace_config: TraceConfig | None = None,
) -> WriteResult:
    """Write the accepted / edited proposals; see the module docstring.

    ``operations`` and ``zones`` are needed to re-apply each operation on the copy.
    ``decided=False`` refuses outright (the caller says decisions are not complete).
    """
    if not decided:
        raise WriteRefused("decisions are not complete")
    skip_ids = set(excluded)
    undecided = [p.id for p in proposals if p.status == "proposed" and p.id not in skip_ids]
    if undecided:
        raise WriteRefused(f"proposals still undecided: {', '.join(undecided)}")
    config = trace_config or TraceConfig()
    index_ops = {o.id: o for o in operations}
    zone_by_id = {z.id: z for z in zones}
    groups: dict[str, list[Proposal]] = {}
    result = WriteResult()
    for proposal in proposals:
        if proposal.id in skip_ids or proposal.status not in APPLIED:
            continue
        zone = zone_by_id.get(proposal.zone_id)
        if zone is None or proposal.operation_id not in index_ops:
            raise WriteRefused(f"{proposal.id}: unknown zone or operation")
        if zone.kind == "illustration":
            result.skipped.append({"proposal": proposal.id, "reason": "flag only (illustration)"})
            continue
        doc = index.docs.get(ref_key(proposal.ref))
        if doc is None:
            raise WriteRefused(f"{proposal.id}: unknown document {ref_key(proposal.ref)}")
        if doc.role != "dm" or not doc.writable:
            result.skipped.append(
                {"proposal": proposal.id, "reason": f"read-only document ({doc.role})"}
            )
            continue
        groups.setdefault(ref_key(proposal.ref), []).append(proposal)

    applied = {p.id for group in groups.values() for p in group}
    for group in groups.values():
        for proposal in group:
            if proposal.replaces in applied:
                raise WriteRefused(
                    f"{proposal.id} and {proposal.replaces} are mutually exclusive "
                    "(one replaces the other): keep only one of them"
                )

    out_dir = Path(run_dir) / "out"
    jobs = []
    for key, group in groups.items():
        doc = index.docs[key]
        if out_dir.resolve() == Path(doc.path).resolve().parent:
            raise WriteRefused("the output folder must not be the source folder")
        try:
            jobs.append(
                _prepare_document(key, doc, group, index_ops, zone_by_id, policy, today, config)
                + (doc,)
            )
        except (OpError, trace.TraceError, versioning.VersioningError) as exc:
            raise WriteRefused(f"{key}: {exc}") from exc
    out_dir.mkdir(parents=True, exist_ok=True)
    for xdoc, new_name, entry, _doc in jobs:
        result.written.append(xio.save(xdoc, out_dir / new_name))
        result.log.append(entry)
    return result
