"""delete_step: designate the step to delete (the deletion itself is a mark, added later)."""

from __future__ import annotations

from typing import Any

from redactech.models import Zone
from redactech.s1000d.ops._common import OpResult, by_id, path_of, step_id_of, xml_of


def delete_step(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Return the step ``step_id`` with ``change_type="delete"``; the tree is NOT changed.

    A deletion keeps the element and marks it (``changeMark``/``changeType``) when the changes
    are written; only a new issue consolidates (removes) it.
    """
    step = by_id(tree, step_id_of(params, zone), "proceduralStep")
    xml = xml_of(step)
    return OpResult(path_of(step), "delete", xml, xml)
