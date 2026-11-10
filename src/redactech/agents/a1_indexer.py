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
    idx: index.CorpusIndex,
    doc: SourceDoc,
    xdoc: object,
    cache: dict[str, object],
    resolve: bool = False,
) -> tuple[list[object], list[CheckResult]]:
    """BREX documents of ``doc`` from the chain stored by ``build_index`` (loaded once each).

    With ``resolve`` the chain is resolved again from the BREX index (after a BREX swap).
    """
    key = index.ref_key(doc.ref)
    entries = [idx.docs.get(index.ref_key(r)) for r in doc.brex_chain]
    if resolve or any(e is None for e in entries):  # not scanned or swapped: the long way
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
    ws: wsmod.Workspace,
    idx: index.CorpusIndex,
    doc: SourceDoc,
    cache: dict[str, object],
    resolve: bool = False,
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
    chain, notes = _brex_chain(idx, doc, xdoc, cache, resolve)
    results += [n.model_copy(update={"ref": doc.ref}) for n in notes]
    results += brex.check_brex(xdoc, chain, doc.ref)
    return results


def _baseline(
    ws: wsmod.Workspace, idx: index.CorpusIndex, resolve: bool = False
) -> list[CheckResult]:
    """The baseline of an index: every data module checked, one bad file never stops it."""
    cache: dict[str, object] = {}
    baseline: list[CheckResult] = []
    for key in sorted(idx.docs):
        doc = idx.docs[key]
        if doc.role != "dm":
            continue
        try:
            baseline += _mark(_check_one(ws, idx, doc, cache, resolve))
        except Exception as exc:  # parse failure or unexpected error: report it, go on
            baseline.append(_problem(doc, f"{Path(doc.path).name} could not be checked: {exc}"))
    return baseline


def run(ws: wsmod.Workspace) -> tuple[index.CorpusIndex, list[CheckResult]]:
    """Index the workspace and compute the baseline. One bad file never stops the run."""
    idx = index.build_index(ws, keep_docs=True)
    baseline = _baseline(ws, idx)
    idx.loaded.clear()  # the parsed documents are only needed during the run
    return idx, baseline


def apply_swap(idx: index.CorpusIndex, new_brex_path: Path | str) -> None:
    """Replace (or add) the BREX of the same DMC in the BREX index of every source.

    The original file is not touched. Raises ``ValueError`` if the name is not a BREX.
    """
    for source_id, mapping in list(idx.brex_index.items()):
        idx.brex_index[source_id] = brex.swap_brex(mapping, new_brex_path)
    if not idx.brex_index:
        raise ValueError("no source to swap the BREX in")


def swap_brex(
    ws: wsmod.Workspace, idx: index.CorpusIndex, new_brex_path: Path | str
) -> list[CheckResult]:
    """Swap a BREX in the index, resolve every chain again, and return the new baseline."""
    apply_swap(idx, new_brex_path)
    return _baseline(ws, idx, resolve=True)


def problems(results: list[CheckResult]) -> list[CheckResult]:
    """Only the results that report something wrong (``ok=False``)."""
    return [r for r in results if not r.ok]
