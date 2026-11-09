"""Shared helpers of the operations: result type, errors, target lookup, serialisation, ids."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal

from lxml import etree

from redactech.models import Zone
from redactech.s1000d import io as xio
from redactech.s1000d.text import substring_spans, token_spans

ChangeType = Literal["add", "modify", "delete"]
INDENT_UNIT = "  "


class OpError(ValueError):
    """An operation cannot be applied (missing parameter, target not found, nothing to do)."""


@dataclass(frozen=True)
class OpResult:
    """What an operation did (or, for deletions, would do) to the tree it was given."""

    element_xpath: str
    change_type: ChangeType
    before_xml: str
    after_xml: str


def require(params: dict[str, Any], *names: str) -> list[Any]:
    """The values of the required parameters, or an ``OpError`` naming the missing ones."""
    missing = [n for n in names if params.get(n) in (None, "")]
    if missing:
        raise OpError(f"missing parameter(s): {', '.join(missing)}")
    return [params[n] for n in names]


def root_of(tree: Any) -> Any:
    return xio.root_of(tree)


def xml_of(el: Any) -> str:
    """Serialisation of one element, standalone: no tail and no inherited, unused namespaces.

    lxml writes the namespace declarations of all the ancestors on a sub-element it serialises
    (``xmlns:xsi``, ``xmlns:xlink`` of the root...). A copy of the element is serialised after
    ``cleanup_namespaces`` instead, so only the declarations the element really uses remain
    (for instance ``xlink`` on a ``dmRef`` with ``xlink:`` attributes).
    """
    clone = copy.deepcopy(el)
    clone.tail = None
    etree.cleanup_namespaces(clone)
    return etree.tostring(clone, encoding="unicode")


def path_of(el: Any) -> str:
    return el.getroottree().getpath(el)


def by_id(tree: Any, element_id: str, tag: str | None = None) -> Any:
    """The element with this ``@id`` (optionally checking its tag), or an ``OpError``."""
    found = xio.xpath(root_of(tree), "//*[@id=$i]", i=element_id)
    if not found:
        raise OpError(f"no element with id {element_id!r}")
    if tag is not None and found[0].tag != tag:
        raise OpError(f"element {element_id!r} is a {found[0].tag}, not a {tag}")
    return found[0]


def target_of(tree: Any, zone: Zone | None) -> Any:
    """The element a zone designates: its ``xpath`` first, then its ``element_id``.

    The xpath comes first because a zone found by the locator carries the id of the NEAREST
    element that has one (for example the step around a part number), not necessarily the
    designated element itself.
    """
    if zone is None:
        raise OpError("operation needs a zone")
    if zone.xpath:
        try:
            found = xio.xpath(tree, zone.xpath)
        except etree.LxmlError as exc:
            raise OpError(f"invalid zone xpath {zone.xpath!r}: {exc}") from exc
        if isinstance(found, list) and found:
            return found[0]
    if zone.element_id:
        found = xio.xpath(root_of(tree), "//*[@id=$i]", i=zone.element_id)
        if found:
            return found[0]
    raise OpError(f"zone target not found ({zone.xpath or zone.element_id or 'empty zone'})")


def new_id(tree: Any, prefix: str) -> str:
    """Smallest unused ``<prefix>NNNN`` above the highest number already used."""
    used = {
        el.get("id") for el in root_of(tree).iter() if isinstance(el.tag, str) and el.get("id")
    }
    highest = 0
    for value in used:
        tail = value[len(prefix) :] if value.startswith(prefix) else ""
        if tail.isdigit():
            highest = max(highest, int(tail))
    number = highest + 1
    while f"{prefix}{number:04d}" in used:
        number += 1
    return f"{prefix}{number:04d}"


def indent_of(el: Any) -> str | None:
    """Whitespace written before ``el`` on its line, or None for compact (unindented) XML."""
    previous = el.getprevious()
    parent = el.getparent()
    if previous is not None:
        before = previous.tail
    else:
        before = parent.text if parent is not None else None
    if before is None or "\n" not in before or before.strip():
        return None
    return before.rsplit("\n", 1)[1]


def place(new: Any, reference: Any, after: bool) -> None:
    """Insert ``new`` next to ``reference``, keeping the line layout of indented XML.

    lxml puts the text that followed ``reference`` after ``new`` when inserting after it, and
    leaves no text between ``new`` and ``reference`` when inserting before it: both cases are
    repaired so each element stays on its own line with the indentation of ``reference``.
    """
    indent = indent_of(reference)
    separator = None if indent is None else "\n" + indent
    if after:
        original = reference.tail
        reference.addnext(new)
        reference.tail = separator
        new.tail = original
    else:
        reference.addprevious(new)
        new.tail = separator


def format_children(el: Any, indent: str | None) -> None:
    """Indent the direct children of a freshly built element (no-op for compact XML)."""
    if indent is None or len(el) == 0:
        return
    inner = indent + INDENT_UNIT
    el.text = "\n" + inner
    for child in el:
        child.tail = "\n" + inner
    el[-1].tail = "\n" + indent


def common_ancestor(a: Any, b: Any) -> Any:
    """Closest element that contains both ``a`` and ``b`` (the root at worst)."""
    ancestors = set(a.iterancestors())  # holding the elements keeps their identity stable
    for candidate in [b, *b.iterancestors()]:
        if candidate in ancestors:
            return candidate
    return a.getroottree().getroot()


def format_tree(el: Any, indent: str | None) -> None:
    """Indent ``el`` and everything below it (no-op for compact XML)."""
    if indent is None:
        return
    format_children(el, indent)
    for child in el:
        format_tree(child, indent + INDENT_UNIT)


def replace_in_texts(
    el: Any, old: str, new: str, occurrence: int | None = None, whole_word: bool = True
) -> int:
    """Replace ``old`` in the own text of ``el`` (its text and the tails of its children).

    ``whole_word`` uses the whole-word rule of ``s1000d.text``; ``occurrence`` (1 = first,
    -1 = last) selects one occurrence among all those of the element. Returns how many were
    replaced. Text nodes are edited as strings: no serialisation, no regular expression.
    """
    finder = token_spans if whole_word else substring_spans
    slots = [(el, "text"), *[(child, "tail") for child in el]]
    values = [getattr(owner, attr) or "" for owner, attr in slots]
    found = [finder(value, old) for value in values]
    total = sum(len(spans) for spans in found)
    if total == 0:
        return 0
    if occurrence is None:
        chosen = set(range(total))
    else:
        index = occurrence - 1 if occurrence > 0 else total + occurrence
        if not 0 <= index < total:
            return 0
        chosen = {index}
    counter = 0
    for (owner, attr), value, spans in zip(slots, values, found, strict=True):
        picked = []
        for span in spans:
            if counter in chosen:
                picked.append(span)
            counter += 1
        if picked:
            for start, end in reversed(picked):
                value = value[:start] + new + value[end:]
            setattr(owner, attr, value)
    return len(chosen)


def step_reference(params: dict[str, Any], zone: Zone | None) -> tuple[str, bool]:
    """``(id of the reference step, insert after it?)`` from ``after_id`` / ``before_id``."""
    after_id, before_id = params.get("after_id"), params.get("before_id")
    if not after_id and not before_id and zone is not None and zone.element_id:
        after_id = zone.element_id
    if bool(after_id) == bool(before_id):
        raise OpError("give exactly one of after_id and before_id")
    return (after_id or before_id), bool(after_id)


def step_id_of(params: dict[str, Any], zone: Zone | None) -> str:
    """``step_id`` from the parameters, else the id of the zone element."""
    value = params.get("step_id") or (zone.element_id if zone is not None else None)
    if not value:
        raise OpError("missing parameter(s): step_id")
    return value
