"""Corpus index: documents, BREX chains and reference tables (parts, links, figures).

Everything is read through the ``io`` helpers (``find`` / ``findall`` / ``xpath``); free text is
searched with plain string operations on already extracted text, never with regular
expressions on XML.

Part number occurrences (``find_part``) have a ``kind``:

``partNumber``  text of a ``partNumber`` element;
``partRef``     ``partRef/@partNumberValue`` (``context`` = enclosing ``catalogSeqNumber``);
``partSpec``    ``partIdent/@partNumberValue`` inside a comrep ``partSpec`` (declaration);
``partIdent``   ``partIdent/@partNumberValue`` anywhere else (for instance in an update file);
``para``        free text: the own text of any element (titles, descriptions, notes...).

Read-only documents (update files, BREX, read-only sources) are indexed too; their
occurrences carry ``writable=False``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from redactech.models import CheckResult, SourceDoc, SourceRef
from redactech.s1000d import brex, ident
from redactech.s1000d import io as xio
from redactech.s1000d.text import contains_token
from redactech.sources import workspace as wsmod

INDEXED_ROLES = ("dm", "upf")
CHAIN_ROLES = ("dm", "brex")
# Free text is read from the own text of EVERY element, except the subtrees below (identification
# and status boilerplate: codes, companies, security, BREX reference...) and metadata elements
# in a namespace. Text of ``partNumber`` is a structured occurrence and is not repeated as text.
DENY_SUBTREES = frozenset(
    {
        "dmIdent",
        "dataRestrictions",
        "responsiblePartnerCompany",
        "originator",
        "security",
        "brexDmRef",
        "applicCrossRefTableRef",
        "qualityAssurance",
        "logo",
        "sourceDmIdent",
        "repositorySourceDmIdent",
        "updateIdent",
        "updateAddress",
        "targetDmIssueInfo",
    }
)
DENY_TEXT = frozenset({"partNumber"})


def ref_key(ref: SourceRef) -> str:
    """Stable string key of a document reference."""
    return f"{ref.source_id}:{ref.doc_key}"


@dataclass(frozen=True)
class Occurrence:
    ref: SourceRef
    kind: str
    xpath: str
    element_id: str | None
    value: str
    writable: bool
    context: str | None = None


@dataclass(frozen=True)
class InternalRef:
    ref: SourceRef
    xpath: str
    element_id: str | None
    target_id: str
    target_type: str
    target_tag: str | None  # tag of the element the id points to, None if it does not exist


@dataclass(frozen=True)
class DmRefEntry:
    ref: SourceRef
    xpath: str
    element_id: str | None
    context_tag: str  # parent element, for instance "brexDmRef" or "refs"
    target: str  # DMC string of the referenced data module
    issue: str | None = None
    in_work: str | None = None


@dataclass
class Figure:
    ref: SourceRef
    xpath: str
    figure_id: str | None
    graphics: list[str] = field(default_factory=list)  # ICN entity names
    referenced_by: list[str] = field(default_factory=list)  # ids (or xpaths) of the referrers


@dataclass(frozen=True)
class TextBlock:
    ref: SourceRef
    xpath: str
    element_id: str | None
    text: str
    writable: bool


@dataclass
class CorpusIndex:
    docs: dict[str, SourceDoc] = field(default_factory=dict)
    brex_index: dict[str, dict[str, Path]] = field(default_factory=dict)  # per source id
    parts: dict[str, list[Occurrence]] = field(default_factory=dict)
    texts: list[TextBlock] = field(default_factory=list)
    internal_refs: dict[str, list[InternalRef]] = field(default_factory=dict)  # by irtt code
    dm_refs: list[DmRefEntry] = field(default_factory=list)
    figures: dict[str, Figure] = field(default_factory=dict)
    warnings: list[CheckResult] = field(default_factory=list)  # BREX chain problems
    unreadable: dict[str, str] = field(default_factory=dict)  # doc key -> parse error
    chain_notes: dict[str, list[CheckResult]] = field(default_factory=dict)  # per doc key
    loaded: dict[str, Any] = field(default_factory=dict)  # XmlDoc kept by keep_docs=True
    sources: dict[str, Any] = field(default_factory=dict)  # workspace Source objects by id

    def counts(self) -> dict[str, dict[str, int]]:
        """Number of documents per source and per role."""
        result: dict[str, dict[str, int]] = {}
        for doc in self.docs.values():
            per_role = result.setdefault(doc.ref.source_id, {})
            per_role[doc.role] = per_role.get(doc.role, 0) + 1
        return result


# --- helpers ------------------------------------------------------------------


def _nearest_id(el: Any) -> str | None:
    node = el
    while node is not None:
        value = node.get("id")
        if value:
            return value
        node = node.getparent()
    return None


def _path(el: Any) -> str:
    return el.getroottree().getpath(el)


def _add_part(index: CorpusIndex, occ: Occurrence) -> None:
    index.parts.setdefault(occ.value, []).append(occ)


def _index_parts(index: CorpusIndex, ref: SourceRef, writable: bool, root: Any) -> None:
    for el in xio.xpath(root, "//partNumber"):
        value = "".join(el.itertext()).strip()
        if value:
            occ = Occurrence(ref, "partNumber", _path(el), _nearest_id(el), value, writable)
            _add_part(index, occ)
    for el in xio.xpath(root, "//partRef[@partNumberValue]"):
        context = xio.xpath(el, "ancestor::catalogSeqNumber[1]")
        occ = Occurrence(
            ref,
            "partRef",
            _path(el),
            _nearest_id(el),
            el.get("partNumberValue"),
            writable,
            _path(context[0]) if context else None,
        )
        _add_part(index, occ)
    for el in xio.xpath(root, "//partIdent[@partNumberValue]"):
        parent = el.getparent()
        kind = "partSpec" if parent is not None and parent.tag == "partSpec" else "partIdent"
        occ = Occurrence(
            ref, kind, _path(el), _nearest_id(el), el.get("partNumberValue"), writable
        )
        _add_part(index, occ)


def _text_blocks(root: Any) -> Iterator[tuple[Any, str]]:
    """``(element, own text)`` for every element that carries text, denied subtrees skipped.

    The own text of an element is its text and the text following each of its children (the
    text of child elements belongs to those children), whitespace-normalised.
    """
    stack = [root]
    while stack:
        el = stack.pop()
        if not isinstance(el.tag, str) or el.tag.startswith("{") or el.tag in DENY_SUBTREES:
            continue
        if el.tag not in DENY_TEXT:
            text = " ".join(" ".join([el.text or "", *[c.tail or "" for c in el]]).split())
            if text:
                yield el, text
        stack.extend(reversed(list(el)))


def _index_text(index: CorpusIndex, ref: SourceRef, writable: bool, root: Any) -> None:
    for el, text in _text_blocks(root):
        index.texts.append(TextBlock(ref, _path(el), _nearest_id(el), text, writable))


def _index_internal_refs(index: CorpusIndex, ref: SourceRef, root: Any) -> None:
    for el in xio.xpath(root, "//internalRef"):
        target_id = el.get("internalRefId") or ""
        target_type = el.get("internalRefTargetType") or ""
        found = xio.xpath(root, "//*[@id=$i]", i=target_id) if target_id else []
        entry = InternalRef(
            ref,
            _path(el),
            _nearest_id(el),
            target_id,
            target_type,
            found[0].tag if found else None,
        )
        index.internal_refs.setdefault(target_type, []).append(entry)


def _index_dm_refs(index: CorpusIndex, ref: SourceRef, root: Any) -> None:
    for el in xio.xpath(root, "//dmRef"):
        code_el = xio.find(el, "dmRefIdent/dmCode")
        if code_el is None:
            continue
        info = xio.find(el, "dmRefIdent/issueInfo")
        parent = el.getparent()
        index.dm_refs.append(
            DmRefEntry(
                ref,
                _path(el),
                _nearest_id(el),
                parent.tag if parent is not None and isinstance(parent.tag, str) else "",
                ident.DmCode.from_element(code_el).dmc_string(),
                info.get("issueNumber") if info is not None else None,
                info.get("inWork") if info is not None else None,
            )
        )


def _index_figures(index: CorpusIndex, ref: SourceRef, root: Any) -> None:
    for el in xio.xpath(root, "//figure"):
        figure_id = el.get("id")
        graphics = [
            g.get("infoEntityIdent") for g in xio.findall(el, "graphic") if g.get("infoEntityIdent")
        ]
        referrers: list[str] = []
        if figure_id:
            for r in xio.xpath(root, "//internalRef[@internalRefId=$i]", i=figure_id):
                if r.get("internalRefTargetType") in (None, "irtt01"):
                    referrers.append(_nearest_id(r) or _path(r))
        key = f"{ref_key(ref)}#{figure_id or _path(el)}"
        index.figures[key] = Figure(ref, _path(el), figure_id, graphics, referrers)


def _ref_for_path(by_path: dict[Path, SourceRef], source_id: str, path: Path) -> SourceRef:
    return by_path.get(path.resolve()) or SourceRef(source_id=source_id, doc_key=path.stem)


# --- build --------------------------------------------------------------------


def build_index(ws: wsmod.Workspace, keep_docs: bool = False) -> CorpusIndex:
    """Scan the workspace and index every data module and update file.

    With ``keep_docs`` the parsed data modules stay in ``index.loaded`` (by document key) so a
    caller that needs them again does not parse them twice; the caller should clear it.
    """
    index = CorpusIndex()
    index.sources = {src.id: src for src in ws.sources}
    docs = wsmod.scan(ws)
    by_path = {Path(d.path).resolve(): d.ref for d in docs}
    for src in ws.sources:
        folders = {*src.brex_dirs}
        folders.update(
            Path(d.path).parent for d in docs if d.ref.source_id == src.id and d.role == "brex"
        )
        index.brex_index[src.id] = brex.index_brex(sorted(folders))
    for doc in docs:
        index.docs[ref_key(doc.ref)] = doc
    for key, doc in list(index.docs.items()):
        if doc.role not in INDEXED_ROLES and doc.role not in CHAIN_ROLES:
            continue
        try:
            xdoc = xio.load(doc.path)
        except Exception as exc:  # unreadable or refused (for instance entity amplification)
            index.unreadable[key] = str(exc)
            continue
        root = xdoc.root
        if keep_docs and doc.role == "dm":
            index.loaded[key] = xdoc
        if doc.role in INDEXED_ROLES:
            _index_parts(index, doc.ref, doc.writable, root)
            _index_text(index, doc.ref, doc.writable, root)
            _index_internal_refs(index, doc.ref, root)
            _index_dm_refs(index, doc.ref, root)
            _index_figures(index, doc.ref, root)
        if doc.role in CHAIN_ROLES:
            notes: list[CheckResult] = []
            chain = brex.resolve_chain(xdoc, index.brex_index.get(doc.ref.source_id, {}), notes)
            refs = [
                _ref_for_path(by_path, doc.ref.source_id, Path(c.path)) for c in chain if c.path
            ]
            index.docs[key] = doc.model_copy(update={"brex_chain": refs})
            index.warnings.extend(notes)
            index.chain_notes[key] = notes
    return index


# --- queries ------------------------------------------------------------------


def find_part(index: CorpusIndex, part_number: str) -> list[Occurrence]:
    """Every occurrence of ``part_number``: structured references, then free text.

    Documents are visited in key order; within a document the order is the one of the document
    (structured kinds first, then free text). Read-only documents are included.
    """
    found = list(index.parts.get(part_number, []))
    for block in index.texts:
        if contains_token(block.text, part_number):
            found.append(
                Occurrence(
                    block.ref, "para", block.xpath, block.element_id, part_number, block.writable
                )
            )
    return sorted(found, key=lambda o: ref_key(o.ref))
