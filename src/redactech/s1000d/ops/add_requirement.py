"""add_requirement: add a spare, supply or tool to the preliminary requirements."""

from __future__ import annotations

from typing import Any

from lxml import etree

from redactech.models import Zone
from redactech.s1000d import io as xio
from redactech.s1000d.ops._common import (
    INDENT_UNIT,
    OpError,
    OpResult,
    format_tree,
    indent_of,
    new_id,
    path_of,
    place,
    require,
    xml_of,
)

# requirement kind -> (container, group, descriptor, "none" placeholder, id prefix)
REQUIREMENTS = {
    "spare": ("reqSpares", "spareDescrGroup", "spareDescr", "noSpares", "spr-"),
    "supply": ("reqSupplies", "supplyDescrGroup", "supplyDescr", "noSupplies", "sup-"),
    "tool": (
        "reqSupportEquips",
        "supportEquipDescrGroup",
        "supportEquipDescr",
        "noSupportEquips",
        "tool-",
    ),
}
REQUIREMENTS["supportEquipment"] = REQUIREMENTS["tool"]


def requirement_spec(params: dict[str, Any]) -> tuple[str, str, str, str, str]:
    (kind,) = require(params, "requirement")
    if kind not in REQUIREMENTS:
        raise OpError(f"unknown requirement kind {kind!r} (expected one of {sorted(REQUIREMENTS)})")
    return REQUIREMENTS[kind]


def preliminary_requirements(tree: Any) -> Any:
    found = xio.xpath(xio.root_of(tree), "//preliminaryRqmts")
    if not found:
        raise OpError("the data module has no preliminaryRqmts")
    return found[0]


def add_requirement(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Add a descriptor to ``preliminaryRqmts``.

    Parameters: ``requirement`` (spare | supply | tool | supportEquipment), ``part_number``,
    ``manufacturer_code`` and ``quantity`` (required: nothing is invented), ``name`` (optional).
    A ``noSpares``-style placeholder is turned into the group; otherwise the descriptor is
    appended to the existing group.
    """
    container_tag, group_tag, descr_tag, none_tag, prefix = requirement_spec(params)
    part_number, manufacturer, quantity = require(
        params, "part_number", "manufacturer_code", "quantity"
    )
    container = preliminary_requirements(tree).find(container_tag)
    if container is None:
        raise OpError(f"preliminaryRqmts has no {container_tag}")

    descr = etree.Element(descr_tag)
    descr.set("id", new_id(tree, prefix))
    if params.get("name"):
        etree.SubElement(descr, "name").text = str(params["name"])
    ident = etree.SubElement(descr, "identNumber")
    etree.SubElement(ident, "manufacturerCode").text = str(manufacturer)
    serial = etree.SubElement(ident, "partAndSerialNumber")
    etree.SubElement(serial, "partNumber").text = str(part_number)
    etree.SubElement(descr, "reqQuantity").text = str(quantity)

    group = container.find(group_tag)
    if group is None:
        placeholder = container.find(none_tag)
        if placeholder is None:
            raise OpError(f"{container_tag} has neither {group_tag} nor {none_tag}")
        placeholder.tag = group_tag  # same position, same line layout
        group = placeholder
    existing = group.findall(descr_tag)
    if existing:
        format_tree(descr, indent_of(existing[-1]))
        place(descr, existing[-1], after=True)
    else:
        group_indent = indent_of(group)
        child_indent = None if group_indent is None else group_indent + INDENT_UNIT
        format_tree(descr, child_indent)
        group.insert(0, descr)
        if child_indent is not None:
            group.text = "\n" + child_indent
            descr.tail = "\n" + group_indent
    return OpResult(path_of(descr), "add", "", xml_of(descr))
