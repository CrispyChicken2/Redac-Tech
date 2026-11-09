"""Versioning policy: suggestion from the operations, and application to a data module.

Policies: ``none`` (issue info untouched), ``in_work`` (``inWork`` + 1) and ``new_issue``
(consolidate, ``issueNumber`` + 1, ``inWork`` back to ``00``). Applying a policy also sets the
issue date and the ``issueType`` and returns the new file name (``ident.filename_for``).
"""

from __future__ import annotations

import datetime
from typing import Any

from redactech.config import TraceConfig
from redactech.models import Operation, VersionPolicy
from redactech.s1000d import ident, trace
from redactech.s1000d import io as xio

MODES = ("none", "in_work", "new_issue")
RANK = {"none": 0, "in_work": 1, "new_issue": 2}
SPARE_KINDS = ("spare", "supply")
STEP_LIMIT = 3  # more than this many steps inserted or deleted => new issue
ISSUE_INFO = "identAndStatusSection/dmAddress/dmIdent/issueInfo"
ISSUE_DATE = "identAndStatusSection/dmAddress/dmAddressItems/issueDate"
DM_STATUS = "identAndStatusSection/dmStatus"


class VersioningError(ValueError):
    """A versioning policy cannot be applied to the data module."""


def _is_number(text: object) -> bool:
    words = str(text).split()
    if not words:
        return False
    try:
        float(words[0].replace(",", "."))
    except ValueError:
        return False
    return True


def _classify(op: Operation) -> tuple[str, str]:
    """``(mode, reason)`` for one operation."""
    params = op.params
    kind = params.get("requirement")
    if op.kind == "update_ref":
        return "in_work", "reference change (update_ref)"
    if op.kind == "replace_text":
        if _is_number(params.get("old", "")) and _is_number(params.get("new", "")):
            return "new_issue", "numeric value change (replace_text)"
        return "in_work", "text change (replace_text)"
    if op.kind == "replace_part":
        if kind in SPARE_KINDS:
            return "new_issue", f"{kind} part number change (replace_part)"
        return "in_work", "part number reference change (replace_part)"
    if op.kind in ("add_requirement", "remove_requirement"):
        if kind in SPARE_KINDS:
            return "new_issue", f"{kind} requirement change ({op.kind})"
        return "in_work", f"tool requirement change ({op.kind})"
    if op.kind in ("insert_step", "delete_step", "move_step"):
        if params.get("warning") or params.get("caution"):
            return "new_issue", f"new warning or caution ({op.kind})"
        return "in_work", f"step change ({op.kind})"
    return "in_work", f"change ({op.kind})"


def suggest_policy(operations: list[Operation]) -> VersionPolicy:
    """Suggest a policy; ``mode`` equals ``suggested`` until the user chooses another.

    Reference, tool and typo changes suggest ``in_work``; spares, supplies, numeric value
    changes, a new warning or caution, and more than three steps inserted or deleted suggest
    ``new_issue``. The strongest trigger wins; ``reasons`` lists every trigger.
    """
    if not operations:
        return VersionPolicy(mode="none", suggested="none", reasons=["no operation"])
    suggested = "in_work"
    reasons: list[str] = []
    for op in operations:
        mode, reason = _classify(op)
        reasons.append(f"{op.id}: {reason} -> {mode}")
        if RANK[mode] > RANK[suggested]:
            suggested = mode
    steps = sum(1 for op in operations if op.kind in ("insert_step", "delete_step"))
    if steps > STEP_LIMIT:
        reasons.append(f"{steps} steps inserted or deleted (more than {STEP_LIMIT}) -> new_issue")
        suggested = "new_issue"
    return VersionPolicy(mode=suggested, suggested=suggested, reasons=reasons)


def _increment(value: str, width: int, name: str) -> str:
    if not value.isdigit():
        raise VersioningError(f"{name} {value!r} is not a number")
    number = int(value) + 1
    if len(str(number)) > width:
        raise VersioningError(f"{name} {value!r} cannot be incremented ({width} digits)")
    return f"{number:0{width}d}"


def apply_policy(
    doc: Any,
    mode: str,
    today: datetime.date | None = None,
    config: TraceConfig | None = None,
    consolidate: bool = True,
) -> str:
    """Apply ``mode`` to the data module in place and return its new file name.

    ``none``: nothing changes. ``in_work``: ``inWork`` + 1. ``new_issue``: consolidate first
    (when ``config.consolidate_on_new_issue`` and ``consolidate``), ``issueNumber`` + 1,
    ``inWork`` = ``00``. For both, ``issueDate`` = ``today`` and, when the attribute exists,
    ``dmStatus/@issueType`` = ``changed`` (``new`` is kept on issue 001).
    """
    if mode not in MODES:
        raise VersioningError(f"unknown versioning mode {mode!r}")
    config = config or TraceConfig()
    root = xio.root_of(doc)
    info = xio.find(root, ISSUE_INFO)
    if info is None:
        raise VersioningError("the data module has no issueInfo")
    issue, in_work = info.get("issueNumber", ""), info.get("inWork", "")
    if mode == "in_work":
        in_work = _increment(in_work, 2, "inWork")
    elif mode == "new_issue":
        if consolidate and config.consolidate_on_new_issue:
            trace.consolidate(doc)
        issue, in_work = _increment(issue, 3, "issueNumber"), "00"
    if mode != "none":
        info.set("issueNumber", issue)
        info.set("inWork", in_work)
        _set_date(root, today or datetime.date.today())
        status = xio.find(root, DM_STATUS)
        if status is not None and status.get("issueType") is not None and issue != "001":
            status.set("issueType", "changed")
    return ident.filename_for(doc, issue, in_work)


def _set_date(root: Any, day: datetime.date) -> None:
    date = xio.find(root, ISSUE_DATE)
    if date is None:
        raise VersioningError("the data module has no issueDate")
    date.set("year", f"{day.year:04d}")
    date.set("month", f"{day.month:02d}")
    date.set("day", f"{day.day:02d}")
