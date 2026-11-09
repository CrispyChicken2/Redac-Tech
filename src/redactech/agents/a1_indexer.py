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


def _check_one(
    ws: wsmod.Workspace, idx: index.CorpusIndex, doc: SourceDoc
) -> list[CheckResult]:
    source = ws.source(doc.ref.source_id)
    xdoc = xio.load(doc.path)
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
    notes: list[CheckResult] = []
    chain = brex.resolve_chain(xdoc, idx.brex_index.get(doc.ref.source_id, {}), notes)
    results += [n.model_copy(update={"ref": doc.ref}) for n in notes]
    results += brex.check_brex(xdoc, chain, doc.ref)
    return results


def run(ws: wsmod.Workspace) -> tuple[index.CorpusIndex, list[CheckResult]]:
    """Index the workspace and compute the baseline. One bad file never stops the run."""
    idx = index.build_index(ws)
    baseline: list[CheckResult] = []
    for key in sorted(idx.docs):
        doc = idx.docs[key]
        if doc.role != "dm":
            continue
        try:
            baseline += _mark(_check_one(ws, idx, doc))
        except Exception as exc:  # parse failure or unexpected error: report it, go on
            baseline.append(_problem(doc, f"{Path(doc.path).name} could not be checked: {exc}"))
    return idx, baseline


def problems(results: list[CheckResult]) -> list[CheckResult]:
    """Only the results that report something wrong (``ok=False``)."""
    return [r for r in results if not r.ok]
