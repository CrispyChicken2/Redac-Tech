"""move_step: move a procedural step to another position."""

from __future__ import annotations

from typing import Any

from redactech.models import Zone
from redactech.s1000d.ops._common import (
    OpError,
    OpResult,
    by_id,
    common_ancestor,
    path_of,
    place,
    step_id_of,
    step_reference,
    xml_of,
)


def move_step(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Move step ``step_id`` after ``after_id`` (or before ``before_id``).

    ``before_xml`` / ``after_xml`` are the closest element containing both positions, before
    and after the move. The step itself is not modified.
    """
    step = by_id(tree, step_id_of(params, zone), "proceduralStep")
    ref_id, after = step_reference(params, None)
    reference = by_id(tree, ref_id, "proceduralStep")
    if reference is step or step in reference.iterancestors():
        raise OpError("a step cannot be moved next to itself or into itself")
    container = common_ancestor(step, reference)
    before = xml_of(container)
    previous, following, tail = step.getprevious(), step.getnext(), step.tail
    step.getparent().remove(step)  # lxml takes the tail text along with the element
    if following is None and previous is not None:
        previous.tail = tail  # the old last child gives its closing indentation back
    place(step, reference, after)
    return OpResult(path_of(step), "modify", before, xml_of(container))
