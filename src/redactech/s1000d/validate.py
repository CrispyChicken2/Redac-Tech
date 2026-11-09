"""Document checks: XSD, integrity, ids, internal links, ICN entities.

Every ``check_*`` function returns a list of ``CheckResult``. A check that finds nothing wrong
returns a single ``ok=True`` result with severity ``info`` (so callers can show that it ran);
callers looking for problems keep the results with ``ok=False``. Schemas are only read from a
local folder (never fetched) and compiled once per path.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import Any

from lxml import etree

from redactech.models import CheckResult, SourceRef
from redactech.s1000d import ident
from redactech.s1000d import io as xio

XSI = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMAS: dict[str, etree.XMLSchema] = {}


# --- helpers ---------------------------------------------------------------------------------


def ref_for(doc: Any, source_id: str = "") -> SourceRef:
    """A ``SourceRef`` for ``doc``: its file name without extension as ``doc_key``."""
    path = getattr(doc, "path", None)
    return SourceRef(source_id=source_id, doc_key=Path(path).stem if path else "")


def _elements(root: Any) -> Iterable[Any]:
    """Elements only (no comments, processing instructions or entity references)."""
    return (el for el in root.iter() if isinstance(el.tag, str))


def _ok(name: str, details: str, ref: SourceRef) -> CheckResult:
    return CheckResult(name=name, ok=True, severity="info", details=details, ref=ref)


def _path_of(el: Any) -> str:
    return el.getroottree().getpath(el)


# --- XSD ---------------------------------------------------------------------------------------


def schema_for(doc: Any, schemas_dir: Path | str) -> Path | None:
    """Local schema file for ``doc``, or None.

    The file name is taken from the root ``xsi:noNamespaceSchemaLocation`` URL (for instance
    ``.../xml_schema_flat/proced.xsd`` gives ``proced.xsd``) and looked up in ``schemas_dir``
    (the flat schemas folder of the document's Issue). Nothing is ever fetched.
    """
    value = xio.root_of(doc).get(f"{{{XSI}}}noNamespaceSchemaLocation")
    if not value:
        return None
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    candidate = Path(schemas_dir) / name
    return candidate if name.endswith(".xsd") and candidate.is_file() else None


def schemas_dir_for(doc: Any, data_dir: Path | str) -> Path | None:
    """``<data_dir>/s1000d-<issue>/schemas`` for the Issue detected in ``doc``, if it exists."""
    issue = ident.detect_issue(doc)
    if issue is None:
        return None
    folder = Path(data_dir) / f"s1000d-{issue}" / "schemas"
    return folder if folder.is_dir() else None


def load_schema(path: Path | str) -> etree.XMLSchema:
    """Compile (once per path) an XSD read with the hardened parser (no network)."""
    resolved = Path(path).resolve()
    key = str(resolved)
    if key not in _SCHEMAS:
        # Parse from bytes with a file URI as base: robust to non-ASCII Windows paths while
        # relative includes/imports (xlink.xsd, ...) still resolve next to the schema.
        tree = etree.parse(
            BytesIO(resolved.read_bytes()), xio.make_parser(), base_url=resolved.as_uri()
        )
        _SCHEMAS[key] = etree.XMLSchema(tree)
    return _SCHEMAS[key]


def check_xsd(
    doc: Any, schemas_dir: Path | str, ref: SourceRef | None = None
) -> list[CheckResult]:
    """Validate ``doc`` against its XSD: one result per error, a warning if no schema is found."""
    ref = ref or ref_for(doc)
    path = schema_for(doc, schemas_dir)
    if path is None:
        return [
            CheckResult(
                name="xsd",
                ok=False,
                severity="warning",
                details=f"schema not found in {schemas_dir}",
                ref=ref,
            )
        ]
    try:
        schema = load_schema(path)
    except etree.LxmlError as exc:
        return [
            CheckResult(
                name="xsd",
                ok=False,
                severity="warning",
                details=f"schema {path.name} could not be compiled: {exc}",
                ref=ref,
            )
        ]
    if schema.validate(xio.tree_of(doc)):
        return [_ok("xsd", f"valid against {path.name}", ref)]
    return [
        CheckResult(
            name="xsd",
            ok=False,
            severity="error",
            details=f"line {entry.line}: {entry.message}",
            ref=ref,
            xpath=entry.path or None,
        )
        for entry in schema.error_log
    ]


# --- integrity, ids, links, ICN ---------------------------------------------------------------


def check_integrity(doc: Any, ref: SourceRef | None = None) -> list[CheckResult]:
    """Root is ``dmodule`` and holds ``identAndStatusSection`` and ``content``."""
    ref = ref or ref_for(doc)
    root = xio.root_of(doc)
    problems: list[str] = []
    if root.tag != "dmodule":
        problems.append(f"root element is {root.tag!r}, expected 'dmodule'")
    else:
        for child in ("identAndStatusSection", "content"):
            if root.find(child) is None:
                problems.append(f"missing {child}")
    if not problems:
        return [_ok("integrity", "dmodule with identAndStatusSection and content", ref)]
    return [
        CheckResult(name="integrity", ok=False, severity="error", details=p, ref=ref, xpath="/")
        for p in problems
    ]


def collect_ids(doc: Any) -> set[str]:
    """All ``@id`` values of the document."""
    return {el.get("id") for el in _elements(xio.root_of(doc)) if el.get("id")}


def check_ids(doc: Any, ref: SourceRef | None = None) -> list[CheckResult]:
    """Report every ``@id`` used more than once (one result per duplicated id)."""
    ref = ref or ref_for(doc)
    root = xio.root_of(doc)
    counts = Counter(el.get("id") for el in _elements(root) if el.get("id"))
    results = []
    seen: Counter = Counter()
    for el in _elements(root):
        value = el.get("id")
        if not value:
            continue
        seen[value] += 1
        if seen[value] == 2:  # report once per duplicated id, at its second occurrence
            results.append(
                CheckResult(
                    name="ids",
                    ok=False,
                    severity="error",
                    details=f"duplicate id {value!r} ({counts[value]} times)",
                    ref=ref,
                    xpath=_path_of(el),
                )
            )
    return results or [_ok("ids", f"{len(counts)} unique ids", ref)]


def check_links(
    doc: Any, known_ids: Iterable[str] | None = None, ref: SourceRef | None = None
) -> list[CheckResult]:
    """Every ``internalRef/@internalRefId`` must target an id of the document.

    ``known_ids`` replaces the ids collected from the document (for callers that already have
    them).
    """
    ref = ref or ref_for(doc)
    root = xio.root_of(doc)
    known = set(known_ids) if known_ids is not None else collect_ids(doc)
    results = []
    checked = 0
    for el in root.iter("internalRef"):
        target = el.get("internalRefId")
        checked += 1
        if not target or target not in known:
            results.append(
                CheckResult(
                    name="links",
                    ok=False,
                    severity="error",
                    details=f"internalRef points to missing id {target!r}",
                    ref=ref,
                    xpath=_path_of(el),
                )
            )
    return results or [_ok("links", f"{checked} internal references resolve", ref)]


def declared_entities(doc: Any) -> set[str]:
    """Names of the entities declared in the DOCTYPE internal subset."""
    tree = xio.tree_of(doc)
    if not hasattr(tree, "docinfo"):
        tree = tree.getroottree()
    names: set[str] = set()
    dtd = tree.docinfo.internalDTD
    if dtd is not None:
        names.update(entity.name for entity in dtd.iterentities())
    # Also read the raw DOCTYPE text kept by ``load`` (regex on the prolog only, not on content).
    subset = getattr(doc, "doctype", None) or ""
    names.update(re.findall(r"<!ENTITY\s+([^\s%]+)", subset))
    return names


def check_icn(
    doc: Any, source_dir: Path | str | None = None, ref: SourceRef | None = None
) -> list[CheckResult]:
    """Each ``graphic/@infoEntityIdent`` is declared as an entity or has an ICN file.

    Missing ones are reported as warnings. ``source_dir`` is searched for a file whose name
    without extension is the ICN.
    """
    ref = ref or ref_for(doc)
    root = xio.root_of(doc)
    declared = declared_entities(doc)
    files: set[str] = set()
    if source_dir is not None and Path(source_dir).is_dir():
        files = {p.stem for p in Path(source_dir).iterdir() if p.is_file()}
    results = []
    checked = 0
    for graphic in root.iter("graphic"):
        name = graphic.get("infoEntityIdent")
        if not name:
            continue
        checked += 1
        if name not in declared and name not in files:
            results.append(
                CheckResult(
                    name="icn",
                    ok=False,
                    severity="warning",
                    details=f"{name} is not declared as an entity and no ICN file was found",
                    ref=ref,
                    xpath=_path_of(graphic),
                )
            )
    return results or [_ok("icn", f"{checked} graphics resolved", ref)]


def check_all(
    doc: Any,
    schemas_dir: Path | str,
    source_dir: Path | str | None = None,
    ref: SourceRef | None = None,
) -> list[CheckResult]:
    """XSD + integrity + ids + links + ICN, in this order."""
    ref = ref or ref_for(doc)
    return [
        *check_xsd(doc, schemas_dir, ref),
        *check_integrity(doc, ref),
        *check_ids(doc, ref=ref),
        *check_links(doc, ref=ref),
        *check_icn(doc, source_dir, ref),
    ]
