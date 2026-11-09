"""BREX (business rules) support: rules, chain resolution and an in-house checker.

The in-house evaluator is the reference implementation. An adapter for ``s1kd-brexcheck`` is
intentionally not provided yet (it would stay optional and off by default).

Rule semantics (``objectPath/@allowedObjectFlag``):

* ``0`` forbidden: a violation for every node the XPath selects (when ``objectValue`` is
  present, only for selected values that match one of them);
* ``1`` mandatory: a violation if the XPath selects nothing (selected values are also checked
  against ``objectValue`` when present);
* ``2`` allowed: with ``objectValue``, a violation for each selected value outside the allowed
  values; without, nothing to check.

``objectValue/@valueForm``: ``single`` exact value, ``range`` ``a~b`` (numeric when both ends
are numbers, else string order, bounds included), ``pattern`` a regular expression applied to
the VALUE string (full match). The value of a selected element is its stripped text content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from redactech.models import CheckResult, SourceRef
from redactech.s1000d import ident
from redactech.s1000d import io as xio

MAX_DEPTH = 10
MAX_VIOLATIONS_PER_RULE = 200
BREX_STATUS_PATH = "identAndStatusSection/dmStatus/brexDmRef/dmRef/dmRefIdent/dmCode"


@dataclass(frozen=True)
class BrexValue:
    form: str  # "single", "range", "pattern" or "" when unspecified (treated as single)
    allowed: str
    label: str = ""


@dataclass(frozen=True)
class BrexRule:
    id: str
    xpath: str
    flag: int  # 0 forbidden, 1 mandatory, 2 allowed
    values: tuple[BrexValue, ...] = field(default_factory=tuple)
    message: str = ""
    brex: str = ""  # DMC string of the BREX the rule comes from

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "xpath": self.xpath,
            "flag": self.flag,
            "message": self.message,
            "brex": self.brex,
        }


def _text(el: Any) -> str:
    return " ".join("".join(el.itertext()).split())


def brex_key(doc: Any) -> str:
    """DMC string of a BREX data module (empty if it has no dmCode)."""
    code = ident.dm_code(doc)
    return code.dmc_string() if code else ""


def load_rules(brex_doc: Any) -> list[BrexRule]:
    """Rules of ``structureObjectRuleGroup/structureObjectRule`` in document order."""
    root = xio.root_of(brex_doc)
    key = brex_key(brex_doc)
    rules = []
    found_rules = root.iterfind(".//structureObjectRuleGroup/structureObjectRule")
    for number, rule in enumerate(found_rules, 1):
        path_el = rule.find("objectPath")
        expr = "".join(path_el.itertext()).strip() if path_el is not None else ""
        if not expr:
            continue
        try:
            flag = int(path_el.get("allowedObjectFlag", "2"))
        except ValueError:
            flag = 2
        values = tuple(
            BrexValue(ov.get("valueForm", ""), ov.get("valueAllowed", ""), _text(ov))
            for ov in rule.findall("objectValue")
        )
        use = rule.find("objectUse")
        rules.append(
            BrexRule(
                id=rule.get("id") or f"{key}#{number}",
                xpath=expr,
                flag=flag,
                values=values,
                message=_text(use) if use is not None else "",
                brex=key,
            )
        )
    return rules


# --- index and chain ----------------------------------------------------------------------------


def _brex_key_from_name(name: str) -> tuple[str, tuple[str, str]] | None:
    parsed = ident.parse_filename(name)
    if parsed is None or parsed.prefix != "DMC":
        return None
    tokens = parsed.code.split("-")
    if len(tokens) < 8 or tokens[6][:3] != ident.BREX_INFO_CODE:
        return None
    return parsed.code, (parsed.issue or "", parsed.in_work or "")


def index_brex(dirs: Any) -> dict[str, Path]:
    """Map DMC string -> BREX file for the BREX data modules found in ``dirs``.

    Only file names are inspected. If several issues of one BREX exist, the latest wins.
    """
    index: dict[str, Path] = {}
    latest: dict[str, tuple[str, str]] = {}
    for folder in dirs:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            found = _brex_key_from_name(path.name)
            if found is None or path.suffix.lower() != ".xml":
                continue
            key, issue = found
            if key not in index or issue > latest[key]:
                index[key] = path
                latest[key] = issue
    return index


def swap_brex(index: dict[str, Path], new_brex_path: Path | str) -> dict[str, Path]:
    """New index where the BREX with the same DMC as ``new_brex_path`` is replaced or added."""
    path = Path(new_brex_path)
    found = _brex_key_from_name(path.name)
    if found is None:
        raise ValueError(f"not a BREX data module file name: {path.name}")
    swapped = dict(index)
    swapped[found[0]] = path
    return swapped


def brex_ref_of(doc: Any) -> str | None:
    """DMC string of the BREX a data module points to (``dmStatus/brexDmRef``), or None."""
    el = xio.find(xio.root_of(doc), BREX_STATUS_PATH)
    return ident.DmCode.from_element(el).dmc_string() if el is not None else None


def resolve_chain(
    doc: Any, brex_index: dict[str, Path], warnings: list[CheckResult] | None = None
) -> list[Any]:
    """BREX documents of ``doc``: its BREX, then that BREX's own BREX, and so on.

    Stops at a BREX that refers to itself, at an unknown BREX (a warning is appended to
    ``warnings`` when given), at a cycle or after ``MAX_DEPTH`` levels. Cycle-safe.
    """
    notes = warnings if warnings is not None else []
    ref = SourceRef(source_id="", doc_key=Path(doc.path).stem if getattr(doc, "path", None) else "")

    def warn(text: str) -> None:
        notes.append(CheckResult(name="brex", ok=False, severity="warning", details=text, ref=ref))

    chain: list[Any] = []
    seen: set[str] = set()
    current = doc
    while len(chain) < MAX_DEPTH:
        key = brex_ref_of(current)
        if key is None:
            if not chain:
                warn("no brexDmRef in the data module")
            break
        if key in seen:
            warn(f"BREX reference cycle at {key}")
            break
        seen.add(key)
        path = brex_index.get(key)
        if path is None:
            warn(f"BREX {key} not found")
            break
        brex_doc = xio.load(path)
        chain.append(brex_doc)
        if brex_ref_of(brex_doc) == key:  # refers to itself: top of the chain
            break
        current = brex_doc
    else:
        warn(f"BREX chain longer than {MAX_DEPTH} levels, stopped")
    return chain


# --- evaluation ---------------------------------------------------------------------------------


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def value_allowed(value: str, brex_value: BrexValue) -> bool:
    """Does ``value`` match this ``objectValue``? (invalid patterns raise ``re.error``)."""
    allowed = brex_value.allowed
    value = value.strip()
    if brex_value.form == "pattern":
        return re.fullmatch(allowed, value) is not None
    if brex_value.form == "range" and "~" in allowed:
        low, high = (part.strip() for part in allowed.split("~", 1))
        nums = (_number(low), _number(value), _number(high))
        if None not in nums:
            return nums[0] <= nums[1] <= nums[2]
        return low <= value <= high
    return value == allowed.strip()


def _node_value(node: Any) -> str:
    if isinstance(node, str):  # attribute value or text() node
        return str(node).strip()
    if hasattr(node, "itertext"):
        return "".join(node.itertext()).strip()
    return str(node).strip()


def _node_path(node: Any) -> str | None:
    try:
        if isinstance(node, str):
            parent = node.getparent()
            if parent is None:
                return None
            where = parent.getroottree().getpath(parent)
            return f"{where}/@{node.attrname}" if getattr(node, "attrname", None) else where
        return node.getroottree().getpath(node)
    except (AttributeError, ValueError):
        return None


def _violation(rule: BrexRule, text: str, ref: SourceRef, xpath: str | None) -> CheckResult:
    return CheckResult(
        name="brex",
        ok=False,
        severity="error",
        details=text,
        rule=rule.as_dict(),
        ref=ref,
        xpath=xpath,
    )


def _warning(rule: BrexRule, text: str, ref: SourceRef) -> CheckResult:
    return CheckResult(
        name="brex",
        ok=False,
        severity="warning",
        details=f"rule {rule.id}: {text}",
        rule=rule.as_dict(),
        ref=ref,
    )


def _capped(found: list[CheckResult], rule: BrexRule, ref: SourceRef) -> list[CheckResult]:
    """Keep the first MAX_VIOLATIONS_PER_RULE violations and say how many were left out."""
    if len(found) <= MAX_VIOLATIONS_PER_RULE:
        return found
    extra = len(found) - MAX_VIOLATIONS_PER_RULE
    note = _warning(rule, f"{extra} more violations not listed", ref)
    return [*found[:MAX_VIOLATIONS_PER_RULE], note]


def _check_rule(doc: Any, rule: BrexRule, ref: SourceRef) -> list[CheckResult]:
    tree = xio.tree_of(doc)
    try:
        selected = tree.xpath(rule.xpath)
    except etree.LxmlError as exc:  # XPathSyntaxError / XPathEvalError and friends
        return [_warning(rule, f"XPath error: {exc}", ref)]
    if not isinstance(selected, list):
        return [_warning(rule, "XPath does not select nodes", ref)]
    why = rule.message or f"BREX rule violated: {rule.xpath}"
    found: list[CheckResult] = []
    if rule.flag == 1 and not selected:
        return [_violation(rule, f"{why} (mandatory object not found)", ref, None)]
    if rule.flag == 0 and not rule.values:
        text = f"{why} (forbidden object found)"
        found = [_violation(rule, text, ref, _node_path(n)) for n in selected]
        return _capped(found, rule, ref)
    for node in selected:
        value = _node_value(node)
        try:
            matches = [value_allowed(value, v) for v in rule.values]
        except re.error as exc:
            return [_warning(rule, f"invalid objectValue pattern: {exc}", ref)]
        if rule.flag == 0 and any(matches):
            text = f"{why} (forbidden value {value!r})"
            found.append(_violation(rule, text, ref, _node_path(node)))
        elif rule.flag in (1, 2) and rule.values and not any(matches):
            text = f"{why} (value {value!r} not allowed)"
            found.append(_violation(rule, text, ref, _node_path(node)))
    return _capped(found, rule, ref)


def check_brex(doc: Any, chain: list[Any], ref: SourceRef | None = None) -> list[CheckResult]:
    """Evaluate every rule of every BREX of ``chain`` on ``doc``.

    Violations are ``ok=False, severity="error"`` with ``rule`` = {id, xpath, flag, message,
    brex}; a rule whose XPath cannot be evaluated gives one ``warning``. Without violation the
    result is one ``ok=True`` info result; with an empty chain, one warning.
    """
    if ref is None:
        path = getattr(doc, "path", None)
        ref = SourceRef(source_id="", doc_key=Path(path).stem if path else "")
    if not chain:
        text = "no BREX to check against"
        return [CheckResult(name="brex", ok=False, severity="warning", details=text, ref=ref)]
    results: list[CheckResult] = []
    checked = 0
    for brex_doc in chain:
        for rule in load_rules(brex_doc):
            checked += 1
            results.extend(_check_rule(doc, rule, ref))
    summary = f"{checked} rules checked, no violation"
    return results or [
        CheckResult(name="brex", ok=True, severity="info", details=summary, ref=ref)
    ]
