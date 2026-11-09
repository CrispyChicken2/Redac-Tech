"""Traceability: reasons for update, change marks, delete marking and consolidation.

* ``ensure_reason`` writes a ``dmStatus/reasonForUpdate`` (unique ``rfu-NNNN`` id) at the place
  the S1000D 4.1 schema expects it: after ``qualityAssurance``, the functional item codes and
  ``skillLevel``, before ``productSafety`` and ``remarks``.
* ``mark`` sets ``changeMark="1"``, ``changeType`` and ``reasonForUpdateRefIds`` on an element.
  Some elements do not accept change attributes (``internalRef``, ``dmCode``, ``issueInfo``,
  inline ``emphasis``...): the mark goes to the NEAREST ancestor that accepts them.
* ``consolidate`` is the only place where an element is physically deleted: on a new issue the
  elements marked ``delete`` disappear and every change mark and reason is cleared.
"""

from __future__ import annotations

from typing import Any

from lxml import etree

from redactech.s1000d import io as xio
from redactech.s1000d.ops._common import format_children, indent_of, new_id, place

CHANGE_TYPES = ("add", "modify", "delete")
CHANGE_ATTRIBUTES = ("changeMark", "changeType", "reasonForUpdateRefIds")
# Elements whose schema type has no change attribute group (checked in the 4.1 flat schemas).
NO_CHANGE_ATTRIBUTES = frozenset(
    {
        "internalRef",
        "dmRefIdent",
        "dmCode",
        "issueInfo",
        "issueDate",
        "language",
        "emphasis",
        "subScript",
        "superScript",
        "verbatimText",
        "reasonForUpdate",
        "dmAddress",
        "dmIdent",
        "dmAddressItems",
    }
)
# Children of dmStatus that come BEFORE reasonForUpdate in the schema sequence.
BEFORE_REASON = frozenset(
    {
        "sourceDmIdent",
        "repositorySourceDmIdent",
        "security",
        "dataRestrictions",
        "logo",
        "responsiblePartnerCompany",
        "originator",
        "applicCrossRefTableRef",
        "applic",
        "applicRef",
        "techStandard",
        "brexDmRef",
        "qualityAssurance",
        "systemBreakdownCode",
        "functionalItemCode",
        "functionalItemRef",
        "skillLevel",
        "reasonForUpdate",
    }
)


class TraceError(ValueError):
    """A trace operation cannot be done (no dmStatus, bad change type...)."""


def _normalised(text: str) -> str:
    return " ".join(text.split())


def ensure_reason(doc: Any, text: str) -> str:
    """The id of a ``reasonForUpdate`` saying ``text`` (an identical one is reused)."""
    root = xio.root_of(doc)
    status = xio.find(root, "identAndStatusSection/dmStatus")
    if status is None:
        raise TraceError("the data module has no dmStatus")
    wanted = _normalised(text)
    if not wanted:
        raise TraceError("a reason for update needs a text")
    for existing in status.findall("reasonForUpdate"):
        if existing.get("id") and _normalised("".join(existing.itertext())) == wanted:
            return existing.get("id")
    reason = etree.Element("reasonForUpdate")
    reason.set("id", new_id(root, "rfu-"))
    etree.SubElement(reason, "simplePara").text = wanted
    anchors = [c for c in status if isinstance(c.tag, str) and c.tag in BEFORE_REASON]
    if anchors:
        format_children(reason, indent_of(anchors[-1]))
        place(reason, anchors[-1], after=True)
    else:
        status.insert(0, reason)
    return reason.get("id")


def mark(element: Any, change_type: str, rfu_id: str | None) -> Any:
    """Mark ``element`` (or its nearest ancestor accepting change attributes) and return it.

    An element already marked ``add`` stays ``add`` when modified again (it is still new in this
    cycle); ``delete`` always wins. Reason ids are appended without duplicates.
    """
    if change_type not in CHANGE_TYPES:
        raise TraceError(f"unknown change type {change_type!r}")
    target = element
    while target is not None and target.tag in NO_CHANGE_ATTRIBUTES:
        target = target.getparent()
    if target is None:
        raise TraceError(f"no element accepting change attributes around {element.tag}")
    current = target.get("changeType")
    if current == "add" and change_type == "modify":
        change_type = "add"
    elif current == "delete":
        change_type = "delete"
    target.set("changeMark", "1")
    target.set("changeType", change_type)
    if rfu_id:
        ids = (target.get("reasonForUpdateRefIds") or "").split()
        if rfu_id not in ids:
            ids.append(rfu_id)
        target.set("reasonForUpdateRefIds", " ".join(ids))
    return target


def detach(element: Any) -> None:
    """Remove ``element`` keeping the indentation of its siblings tidy."""
    parent = element.getparent()
    previous, following, tail = element.getprevious(), element.getnext(), element.tail
    parent.remove(element)  # lxml takes the tail text along with the element
    if following is None and previous is not None:
        previous.tail = tail  # the last child hands the closing indentation back


def consolidate(doc: Any) -> tuple[int, int]:
    """New issue: remove the elements marked ``delete``, all marks and all reasons.

    Returns ``(removed elements, removed reasons)``. This is the only physical deletion.
    """
    root = xio.root_of(doc)
    marked = [e for e in root.iter() if isinstance(e.tag, str) and e.get("changeType") == "delete"]
    marked_set = set(marked)
    outermost = [e for e in marked if not any(a in marked_set for a in e.iterancestors())]
    for element in outermost:
        detach(element)
    reasons = [e for e in root.iter("reasonForUpdate")]
    for reason in reasons:
        detach(reason)
    for element in root.iter():
        if isinstance(element.tag, str):
            for name in CHANGE_ATTRIBUTES:
                if name in element.attrib:
                    del element.attrib[name]
    return len(outermost), len(reasons)
