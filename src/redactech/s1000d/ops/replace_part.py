"""replace_part: rewrite a part number where a zone says it occurs."""

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
from redactech.s1000d.text import replace_token

ATTRIBUTE_TAGS = ("partRef", "partIdent")


def _rewrite(el: Any, old: str, new: str, occurrence: int | None) -> bool:
    if el.tag in ATTRIBUTE_TAGS:
        if (el.get("partNumberValue") or "").strip() != old:
            return False
        el.set("partNumberValue", new)
        return True
    if el.tag == "partNumber":
        text, count = replace_token(el.text or "", old, new, occurrence)
        if count:
            el.text = text
        return bool(count)
    return replace_in_texts(el, old, new, occurrence) > 0  # free text of the element


def replace_part(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Replace part number ``old`` by ``new`` at the zone.

    The zone designates a ``partNumber`` element (its text), a ``partRef`` or ``partIdent``
    (its ``partNumberValue`` attribute, comrep declarations included) or any element whose own
    text mentions the part number (whole-word replacement in the text nodes). ``occurrence``
    (1 = first, -1 = last) limits a free-text replacement to one mention. The only value
    written is ``new``.
    """
    old, new = require(params, "old", "new")
    occurrence = params.get("occurrence")
    el = target_of(tree, zone)
    before = xml_of(el)
    if not _rewrite(el, str(old), str(new), occurrence):
        raise OpError(f"part number {old!r} not found at the zone")
    return OpResult(path_of(el), "modify", before, xml_of(el))
