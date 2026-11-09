"""A4 - locator: where does an operation apply?

For ``replace_part`` EVERY occurrence of the old part number known to the corpus index becomes
a zone (structured occurrences are ``certain``, free-text mentions ``probable``). Occurrences in
read-only documents (update files, BREX, read-only sources) never become zones: they are listed
in ``LocateResult.skipped_readonly`` with the reason. Figures linked to a modified element give
extra zones of kind ``illustration`` and certainty ``to_check`` (the tool never edits images).
Other operations get one zone from their target.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from redactech.models import Operation, SourceRef, Zone
from redactech.s1000d.index import CorpusIndex, Figure, Occurrence, find_part, ref_key

WRITABLE_ROLES = ("dm",)
CONTAINER_TAGS = ("proceduralStep", "levelledPara", "catalogSeqNumber", "description")
STRUCTURED_KINDS = ("partNumber", "partRef", "partSpec", "partIdent")


@dataclass(frozen=True)
class SkippedZone:
    """An occurrence that is reported but never changed."""

    ref: SourceRef
    xpath: str
    kind: str
    reason: str


@dataclass
class LocateResult:
    zones: list[Zone] = field(default_factory=list)
    skipped_readonly: list[SkippedZone] = field(default_factory=list)

    @property
    def content_zones(self) -> list[Zone]:
        return [z for z in self.zones if z.kind == "content"]

    @property
    def illustration_zones(self) -> list[Zone]:
        return [z for z in self.zones if z.kind == "illustration"]


class LocateError(ValueError):
    """The operation cannot be located (for instance an unknown parameter or no target)."""


def _container_prefix(xpath: str) -> str:
    """Path of the closest step / paragraph-like container of ``xpath`` (or ``xpath`` itself)."""
    parts = xpath.split("/")
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].split("[")[0] in CONTAINER_TAGS:
            return "/".join(parts[: i + 1])
    return xpath


def _linked_figures(index: CorpusIndex, occ: Occurrence) -> list[Figure]:
    """Figures of the same document that the modified element is linked to."""
    found: dict[str, Figure] = {}
    if occ.context is not None:  # an illustrated parts item: the figures of its catalogue
        for key, figure in index.figures.items():
            if ref_key(figure.ref) == ref_key(occ.ref):
                found[key] = figure
    prefix = _container_prefix(occ.xpath)
    for entry in index.internal_refs.get("irtt01", []):
        if ref_key(entry.ref) != ref_key(occ.ref):
            continue
        if entry.xpath == prefix or entry.xpath.startswith(prefix + "/"):
            key = f"{ref_key(occ.ref)}#{entry.target_id}"
            if key in index.figures:
                found[key] = index.figures[key]
    return list(found.values())


def _locate_replace_part(op: Operation, index: CorpusIndex) -> LocateResult:
    old = op.params.get("old")
    if not old:
        raise LocateError("replace_part needs the 'old' part number")
    result = LocateResult()
    seen_figures: set[str] = set()
    for occ in find_part(index, str(old)):
        doc = index.docs.get(ref_key(occ.ref))
        if doc is None or not occ.writable or doc.role not in WRITABLE_ROLES:
            role = doc.role if doc is not None else "unknown"
            result.skipped_readonly.append(
                SkippedZone(occ.ref, occ.xpath, occ.kind, f"read-only document ({role})")
            )
            continue
        number = len(result.content_zones) + 1
        certain = occ.kind in STRUCTURED_KINDS
        result.zones.append(
            Zone(
                id=f"zone-{op.id}-{number}",
                ref=occ.ref,
                xpath=occ.xpath,
                element_id=occ.element_id,
                certainty="certain" if certain else "probable",
                found_by="code",
                kind="content",
                reason=f"{occ.kind} {old} in {occ.ref.doc_key}",
                operation_id=op.id,
            )
        )
        for figure in _linked_figures(index, occ):
            key = f"{ref_key(figure.ref)}#{figure.figure_id or figure.xpath}"
            if key in seen_figures:
                continue
            seen_figures.add(key)
            label = figure.figure_id or figure.xpath
            result.zones.append(
                Zone(
                    id=f"zone-{op.id}-fig-{len(seen_figures)}",
                    ref=figure.ref,
                    xpath=figure.xpath,
                    element_id=figure.figure_id,
                    certainty="to_check",
                    found_by="code",
                    kind="illustration",
                    reason=f"figure {label} is linked to the modified {occ.kind}; check the image",
                    operation_id=op.id,
                )
            )
    return result


def _locate_target(op: Operation, index: CorpusIndex) -> LocateResult:
    target = op.target
    if target.ref is None:
        raise LocateError(f"{op.kind} needs a target document")
    key = ref_key(target.ref)
    doc = index.docs.get(key)
    if doc is None:
        raise LocateError(f"unknown document {key}")
    result = LocateResult()
    if doc.role not in WRITABLE_ROLES or not doc.writable:
        result.skipped_readonly.append(
            SkippedZone(target.ref, target.xpath or "", op.kind, f"read-only document ({doc.role})")
        )
        return result
    element_id = (
        target.element_id
        or op.params.get("step_id")
        or op.params.get("after_id")
        or op.params.get("before_id")
    )
    result.zones.append(
        Zone(
            id=f"zone-{op.id}-1",
            ref=target.ref,
            xpath=target.xpath or "",
            element_id=element_id,
            certainty="certain",
            found_by="code",
            kind="content",
            reason=f"{op.kind} target",
            operation_id=op.id,
        )
    )
    return result


def locate(op: Operation, index: CorpusIndex) -> LocateResult:
    """Zones of ``op`` in the corpus (see the module docstring)."""
    if op.kind == "replace_part":
        return _locate_replace_part(op, index)
    return _locate_target(op, index)
