"""replace_text: replace a text (typo, wording) in the text nodes under a zone."""

from __future__ import annotations

from typing import Any

from redactech.models import Zone
from redactech.s1000d.ops._common import (
    OpError,
    OpResult,
    path_of,
    replace_in_texts,
    require,
    target_of,
    xml_of,
)


def replace_text(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Replace ``old`` by ``new`` in the text nodes of the zone element.

    ``scope``: ``"descendants"`` (default) also covers the elements below the zone,
    ``"element"`` only its own text. ``whole_word`` (default False) applies the whole-word rule;
    ``occurrence`` (1 = first, -1 = last) limits the replacement to one mention per element.
    The only value written is ``new``.
    """
    old, new = require(params, "old", "new")
    scope = params.get("scope", "descendants")
    if scope not in ("element", "descendants"):
        raise OpError(f"unknown scope {scope!r}")
    whole_word = bool(params.get("whole_word", False))
    occurrence = params.get("occurrence")
    el = target_of(tree, zone)
    before = xml_of(el)
    elements = [el] if scope == "element" else [e for e in el.iter() if isinstance(e.tag, str)]
    count = sum(replace_in_texts(e, str(old), str(new), occurrence, whole_word) for e in elements)
    if not count:
        raise OpError(f"text {old!r} not found at the zone")
    return OpResult(path_of(el), "modify", before, xml_of(el))
