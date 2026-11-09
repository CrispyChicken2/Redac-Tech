"""Canonical comparison of documents and listing of the elements that changed.

``changed_elements`` is meant to assert "nothing changed outside the expected changes": it
reports the deepest elements whose own content differs, not their ancestors.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from redactech.s1000d import io as xio

Key = str


def c14n_equal(a: Any, b: Any) -> bool:
    """True if two documents (or elements) have the same C14N 1.0 form, comments ignored."""
    return xio.canonical(a) == xio.canonical(b)


def _norm(text: str | None, strip: bool) -> str:
    text = text or ""
    return " ".join(text.split()) if strip else text


def _keys(root: Any) -> dict[Any, Key]:
    """Key of each element, stable when siblings are inserted elsewhere.

    ``id:<value>`` when the id is unique in the document; otherwise the key of the parent plus
    ``/<tag>[<n>]`` (position among the same-tag siblings), so an element without id is matched
    relative to its nearest ancestor that has an id.
    """
    elements = [el for el in root.iter() if isinstance(el.tag, str)]
    ids = Counter(el.get("id") for el in elements if el.get("id"))
    keys: dict[Any, Key] = {}
    for el in elements:  # document order: a parent is always keyed before its children
        value = el.get("id")
        if value and ids[value] == 1:
            keys[el] = f"id:{value}"
            continue
        parent = el.getparent()
        prefix = keys[parent] if parent is not None else ""
        same = 1 + sum(1 for s in el.itersiblings(preceding=True) if s.tag == el.tag)
        keys[el] = f"{prefix}/{el.tag}[{same}]"
    return keys


def _shallow(el: Any, strip: bool) -> tuple:
    """Own content of an element, independent of how many child elements it has.

    Tag, attributes, leading text, the non-blank text between its children (mixed content),
    and its comments, processing instructions and entity references.
    """
    attrs = tuple(sorted(el.attrib.items()))
    tails = []
    others = []
    for child in el:
        if child.tail and child.tail.strip():
            tails.append(_norm(child.tail, strip))
        if not isinstance(child.tag, str):
            name = getattr(child.tag, "__name__", "node")
            others.append((name, getattr(child, "target", ""), child.text))
    return el.tag, attrs, _norm(el.text, strip), tuple(tails), tuple(others)


def _order(el: Any, keys: dict[Any, Key], common: set[Key]) -> list[Key]:
    return [keys[c] for c in el if isinstance(c.tag, str) and keys[c] in common]


def changed_elements(before: Any, after: Any, strip_whitespace: bool = False) -> list[str]:
    """XPaths of the elements that differ between ``before`` and ``after``.

    Elements are matched by their unique ``@id`` when they have one, else by their position
    below the nearest ancestor that has an id (or below the root). Reported: elements whose
    own content differs, elements whose children were reordered, added subtrees (their top
    element only, path in ``after``) and removed subtrees
    (their top element only, path in ``before``). Ancestors of a change are not reported.
    """
    root_b, root_a = xio.root_of(before), xio.root_of(after)
    keys_b, keys_a = _keys(root_b), _keys(root_a)
    by_key_b = {key: el for el, key in keys_b.items()}
    by_key_a = {key: el for el, key in keys_a.items()}
    common = set(by_key_b) & set(by_key_a)
    tree_b, tree_a = root_b.getroottree(), root_a.getroottree()
    changed: list[str] = []

    for el, key in keys_a.items():  # document order of ``after``
        parent = el.getparent()
        if key not in by_key_b:
            if parent is None or keys_a.get(parent) in by_key_b:
                changed.append(tree_a.getpath(el))
            continue
        old = by_key_b[key]
        if _shallow(old, strip_whitespace) != _shallow(el, strip_whitespace):
            changed.append(tree_a.getpath(el))
        elif _order(old, keys_b, common) != _order(el, keys_a, common):
            changed.append(tree_a.getpath(el))

    for el, key in keys_b.items():
        if key in by_key_a:
            continue
        parent = el.getparent()
        if parent is None or keys_b.get(parent) in by_key_a:
            changed.append(tree_b.getpath(el))
    return changed
