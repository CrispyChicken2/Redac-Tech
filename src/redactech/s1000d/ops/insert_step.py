"""insert_step: add a procedural step next to an existing one."""

from __future__ import annotations

from typing import Any

from lxml import etree

from redactech.models import Zone
from redactech.s1000d.ops._common import (
    OpResult,
    by_id,
    format_children,
    indent_of,
    new_id,
    path_of,
    place,
    require,
    step_reference,
    xml_of,
)


def insert_step(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Add a step with one paragraph after ``after_id`` or before ``before_id``.

    ``para`` is the text of the paragraph and the optional ``note`` the text of a note put
    before it (the only texts written); the new step gets a unique
    ``stp-NNNN`` id. Without ``after_id``/``before_id`` the zone element is the step to follow.
    """
    (text,) = require(params, "para")
    ref_id, after = step_reference(params, zone)
    reference = by_id(tree, ref_id, "proceduralStep")
    step = etree.Element("proceduralStep")
    step.set("id", new_id(tree, "stp-"))
    if params.get("note"):  # a note before the paragraph (the project BREX may forbid it)
        etree.SubElement(etree.SubElement(step, "note"), "notePara").text = str(params["note"])
    etree.SubElement(step, "para").text = str(text)
    format_children(step, indent_of(reference))
    place(step, reference, after)
    return OpResult(path_of(step), "add", "", xml_of(step))
