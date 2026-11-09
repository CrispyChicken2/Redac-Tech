"""A1 - workspace indexer: builds the corpus index and the baseline of pre-existing problems.

The baseline runs the document checks on every data module (role ``dm``) before any change:
XSD (when the source has a schemas folder), integrity, ids, links, ICN and the BREX chain.
Every result is marked ``origin="pre_existing"``. All results are returned, including the
``ok=True`` info results of checks that found nothing: count problems with ``ok=False`` only.
"""

from __future__ import annotations

from pathlib import Path

from redactech.models import CheckResult, SourceDoc
from redactech.s1000d import brex, index, validate
from redactech.s1000d import io as xio
from redactech.sources import workspace as wsmod


def _mark(results: list[CheckResult]) -> list[CheckResult]:
    return [r.model_copy(update={"origin": "pre_existing"}) for r in results]


def _problem(doc: SourceDoc, details: str) -> CheckResult:
    return CheckResult(
        name="integrity",
        ok=False,
        severity="error",
        details=details,
        origin="pre_existing",
        ref=doc.ref,
        xpath="/",
    )


def _brex_chain(
    idx: index.CorpusIndex, doc: SourceDoc, xdoc: object, cache: dict[str, object]
) -> tuple[list[object], list[CheckResult]]:
    """BREX documents of ``doc`` from the chain stored by ``build_index`` (loaded once each)."""
    key = index.ref_key(doc.ref)
    entries = [idx.docs.get(index.ref_key(r)) for r in doc.brex_chain]
    if any(e is None for e in entries):  # a BREX that was not scanned: resolve it the long way
        notes: list[CheckResult] = []
        index_for_source = idx.brex_index.get(doc.ref.source_id, {})
        return brex.resolve_chain(xdoc, index_for_source, notes), notes
    chain = []
    for entry in entries:
        path = str(entry.path)
        if path not in cache:
            cache[path] = xio.load(path)
        chain.append(cache[path])
    return chain, list(idx.chain_notes.get(key, []))


def _check_one(
    ws: wsmod.Workspace, idx: index.CorpusIndex, doc: SourceDoc, cache: dict[str, object]
) -> list[CheckResult]:
    source = ws.source(doc.ref.source_id)
    key = index.ref_key(doc.ref)
    xdoc = idx.loaded.get(key) or xio.load(doc.path)
    results: list[CheckResult] = []
    if source.schemas_dir is not None:
        results += validate.check_xsd(xdoc, source.schemas_dir, doc.ref)
    else:
        results.append(
            CheckResult(
                name="xsd",
                ok=True,
                severity="info",
                details="XSD check skipped: no schemas folder for this source",
                ref=doc.ref,
            )
        )
    results += validate.check_integrity(xdoc, doc.ref)
    results += validate.check_ids(xdoc, doc.ref)
    results += validate.check_links(xdoc, ref=doc.ref)
    results += validate.check_icn(xdoc, source.path, doc.ref)
    chain, notes = _brex_chain(idx, doc, xdoc, cache)
    results += [n.model_copy(update={"ref": doc.ref}) for n in notes]
    results += brex.check_brex(xdoc, chain, doc.ref)
    return results


def run(ws: wsmod.Workspace) -> tuple[index.CorpusIndex, list[CheckResult]]:
    """Index the workspace and compute the baseline. One bad file never stops the run."""
    idx = index.build_index(ws, keep_docs=True)
    cache: dict[str, object] = {}
    baseline: list[CheckResult] = []
    for key in sorted(idx.docs):
        doc = idx.docs[key]
        if doc.role != "dm":
            continue
        try:
            baseline += _mark(_check_one(ws, idx, doc, cache))
        except Exception as exc:  # parse failure or unexpected error: report it, go on
            baseline.append(_problem(doc, f"{Path(doc.path).name} could not be checked: {exc}"))
    idx.loaded.clear()  # the parsed documents are only needed during the run
    return idx, baseline


def problems(results: list[CheckResult]) -> list[CheckResult]:
    """Only the results that report something wrong (``ok=False``)."""
    return [r for r in results if not r.ok]
