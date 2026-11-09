"""Operations on a data module tree: one pure function per operation.

Every operation has the signature ``op(tree, zone, params) -> OpResult``. ``tree`` is an lxml
tree (or root element) that the caller has COPIED: operations edit it in place and never touch
files. Values written come only from ``params`` (plus generated unique ids). Deletions do not
remove anything: they designate the element and return ``change_type="delete"``; marking is
done when the changes are written, and only a new issue consolidates.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from redactech.models import Zone
from redactech.s1000d.ops._common import OpError, OpResult
from redactech.s1000d.ops.add_requirement import add_requirement
from redactech.s1000d.ops.delete_step import delete_step
from redactech.s1000d.ops.insert_step import insert_step
from redactech.s1000d.ops.move_step import move_step
from redactech.s1000d.ops.remove_requirement import remove_requirement
from redactech.s1000d.ops.replace_part import replace_part
from redactech.s1000d.ops.replace_text import replace_text
from redactech.s1000d.ops.update_ref import update_ref

Op = Callable[[Any, "Zone | None", dict[str, Any]], OpResult]

OPS: dict[str, Op] = {
    "replace_part": replace_part,
    "replace_text": replace_text,
    "insert_step": insert_step,
    "delete_step": delete_step,
    "move_step": move_step,
    "update_ref": update_ref,
    "add_requirement": add_requirement,
    "remove_requirement": remove_requirement,
}

__all__ = [
    "OPS",
    "OpError",
    "OpResult",
    "add_requirement",
    "apply",
    "copy_tree",
    "delete_step",
    "insert_step",
    "move_step",
    "remove_requirement",
    "replace_part",
    "replace_text",
    "update_ref",
]


def copy_tree(tree: Any) -> Any:
    """An independent copy of a tree (operations are applied to copies)."""
    return copy.deepcopy(tree)


def apply(tree: Any, kind: str, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Run the operation ``kind``; ``OpError`` if the prototype does not implement it."""
    if kind not in OPS:
        raise OpError(f"operation {kind!r} is not implemented")
    return OPS[kind](tree, zone, params)
