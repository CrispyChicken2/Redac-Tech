"""A7 - checker: do the changes introduce problems, or were the problems already there?

``check_proposal`` applies a proposal (with its trace marks, exactly as A11 would) on an
in-memory copy and runs XSD, integrity, ids, links, ICN and the BREX chain. Every FAILING result
is then classified against the baseline of the original document:

* ``pre_existing``: an equivalent failure is in the baseline (OBJ-22: never blamed on the tool);
* ``introduced``: anything else (REQ-11: none may be delivered).

*Matching key* of a failure (line numbers and node positions are ignored because a change can
shift them): ``xsd`` -> (name, message without the ``line N:`` prefix); ``brex`` -> (name, rule
id, message, which carries the offending value); any other check -> (name, message). Equal keys
are matched one to one: if the baseline has two of a kind and the result three, one is introduced.

A ``veracity`` check (OBJ-3) adds an ``introduced`` error for every value that appears in the
changed element but neither before nor in the request (operation parameters and the quotes of
its source); generated ``id`` attributes are exempt, and so are manually edited proposals.
Results are returned (only failures; an empty list means everything passed), the caller stores
them in ``proposal.checks``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from lxml import etree

from redactech.agents.a11_writer import WriteRefused, apply_to_copy
from redactech.models import CheckResult, Operation, Proposal, SourceRef, Zone
from redactech.s1000d import brex, validate
from redactech.s1000d import io as xio
from redactech.s1000d.index import CorpusIndex, ref_key

# --- classification -----------------------------------------------------------


def _strip_line(details: str) -> str:
    if details.startswith("line ") and ": " in details:
        return details.split(": ", 1)[1]
    return details


def result_key(result: CheckResult) -> tuple[str, ...]:
    """The key two failures must share to count as the same problem (see the module docstring)."""
    if result.name == "xsd":
        return (result.name, _strip_line(result.details))
    if result.name == "brex":
        return (result.name, str((result.rule or {}).get("id", "")), result.details)
    return (result.name, result.details)


def classify(
    failing: Iterable[CheckResult], baseline: Iterable[CheckResult], original: SourceRef
) -> list[CheckResult]:
    """Set ``origin``: ``pre_existing`` if the baseline of ``original`` has the failure."""
    wanted = ref_key(original)
    available: Counter[tuple[str, ...]] = Counter(
        result_key(r)
        for r in baseline
        if not r.ok and r.ref is not None and ref_key(r.ref) == wanted
    )
    classified = []
    for result in failing:
        key = result_key(result)
        if available[key] > 0:
            available[key] -= 1
            origin = "pre_existing"
        else:
            origin = "introduced"
        classified.append(result.model_copy(update={"origin": origin}))
    return classified


# --- the checks themselves ----------------------------------------------------


def run_checks(xdoc: Any, index: CorpusIndex, source_id: str, ref: SourceRef) -> list[CheckResult]:
    """XSD + integrity + ids + links + ICN + BREX on a loaded document; failures only."""
    source = index.sources.get(source_id)
    results: list[CheckResult] = []
    if source is not None and source.schemas_dir is not None:
        results += validate.check_xsd(xdoc, source.schemas_dir, ref)
    results += validate.check_integrity(xdoc, ref)
    results += validate.check_ids(xdoc, ref=ref)
    results += validate.check_links(xdoc, ref=ref)
    results += validate.check_icn(xdoc, source.path if source is not None else None, ref)
    notes: list[CheckResult] = []
    chain = brex.resolve_chain(xdoc, index.brex_index.get(source_id, {}), notes)
    results += [n.model_copy(update={"ref": ref}) for n in notes]
    results += brex.check_brex(xdoc, chain, ref)
    return [r for r in results if not r.ok]


def check_doc(
    xdoc: Any,
    index: CorpusIndex,
    baseline: list[CheckResult],
    *,
    original: SourceRef,
    ref: SourceRef | None = None,
) -> list[CheckResult]:
    """Classified failures of a whole (output) document.

    ``original`` is the reference of the source document (its baseline is the comparison and
    its source gives the schemas and BREX); ``ref`` is the reference put on the results (the
    output file, which may have another name after versioning).
    """
    failing = run_checks(xdoc, index, original.source_id, ref or original)
    return classify(failing, baseline, original)


# --- veracity -----------------------------------------------------------------


PUNCTUATION = ".,;:!?()[]\"'"


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _strings(item)
    elif value is not None:
        yield str(value)


def _values(xml: str) -> set[str]:
    """Attribute values (except ids) and stripped text pieces of a serialised element."""
    if not xml.strip():
        return set()
    try:
        root = etree.fromstring(xml.encode("utf-8"), xio.make_parser())
    except etree.LxmlError:
        return set()
    found: set[str] = set()
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        found.update(v for name, v in el.attrib.items() if name != "id")
        for text in (el.text, el.tail):
            if text and text.strip():
                found.add(text.strip())
    return found


def _tokens(value: str) -> set[str]:
    return {tok for tok in (w.strip(PUNCTUATION) for w in value.split()) if tok}


def _supported(value: str, allowed: set[str], old_tokens: set[str]) -> bool:
    """A new value is the whole of a request value, or the old text with request substitutions.

    Whole tokens only: a request value "2" supports the value "2" but not "22" or "Check 2".
    """
    if value in allowed:
        return True
    return all(tok in allowed or tok in old_tokens for tok in _tokens(value))


def veracity_failures(proposal: Proposal, operation: Operation) -> list[CheckResult]:
    """One ``introduced`` error per new value that the request does not contain (OBJ-3).

    A new value must equal a request value (operation parameters, nested ones included, and
    the quotes of its source) or be made of old tokens and request values (an old text in which
    a request value was substituted). Substrings do not count.
    """
    if proposal.status == "edited":
        return []  # the values were typed by the writer
    allowed = {s for s in _strings(operation.params) if s}
    allowed.update(span.quote for span in operation.source if span.quote)
    before = _values(proposal.before_xml)
    old_tokens = set().union(*(_tokens(v) for v in before)) if before else set()
    new = _values(proposal.after_xml) - before
    return [
        CheckResult(
            name="veracity",
            ok=False,
            severity="error",
            details=f"value {value!r} is neither in the document nor in the request",
            origin="introduced",
            ref=proposal.ref,
        )
        for value in sorted(new)
        if not _supported(value, allowed, old_tokens)
    ]


def check_proposal(
    proposal: Proposal,
    index: CorpusIndex,
    baseline: list[CheckResult],
    *,
    operation: Operation,
    zone: Zone,
) -> list[CheckResult]:
    """Failures of ``proposal`` classified as ``pre_existing`` or ``introduced`` (+ veracity).

    ``operation`` and ``zone`` are needed to re-apply the change on a copy (a proposal only
    carries their ids). An illustration zone gives its "to check" warning and nothing else.
    """
    if zone.kind == "illustration":
        return [
            CheckResult(
                name="illustration",
                ok=False,
                severity="warning",
                details=f"to check: {zone.reason}",
                ref=zone.ref,
                xpath=zone.xpath or None,
            )
        ]
    try:
        xdoc = apply_to_copy(index, proposal, operation, zone)
    except WriteRefused as exc:
        return [
            CheckResult(
                name="integrity",
                ok=False,
                severity="error",
                details=f"the proposal cannot be applied: {exc}",
                origin="introduced",
                ref=proposal.ref,
            )
        ]
    failing = run_checks(xdoc, index, proposal.ref.source_id, proposal.ref)
    return classify(failing, baseline, proposal.ref) + veracity_failures(proposal, operation)

