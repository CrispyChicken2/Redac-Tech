"""update_ref: point a dmRef or an internalRef at another target."""

from __future__ import annotations

from typing import Any

from lxml import etree

from redactech.models import Zone
from redactech.s1000d import ident
from redactech.s1000d import io as xio
from redactech.s1000d.ops._common import (
    OpError,
    OpResult,
    by_id,
    path_of,
    require,
    target_of,
    xml_of,
)

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
DM_CODE_ATTRS = (
    "modelIdentCode",
    "systemDiffCode",
    "systemCode",
    "subSystemCode",
    "subSubSystemCode",
    "assyCode",
    "disassyCode",
    "disassyCodeVariant",
    "infoCode",
    "infoCodeVariant",
    "itemLocationCode",
    "learnCode",
    "learnEventCode",
)


def _update_dm_ref(el: Any, params: dict[str, Any]) -> None:
    (spec,) = require(params, "dm_code")
    unknown = sorted(set(spec) - set(DM_CODE_ATTRS))
    if unknown:
        raise OpError(f"unknown dmCode attribute(s): {', '.join(unknown)}")
    code = xio.find(el, "dmRefIdent/dmCode")
    if code is None:
        raise OpError("dmRef without dmRefIdent/dmCode")
    old_key = ident.DmCode.from_element(code).dmc_string()
    for name, value in spec.items():
        code.set(name, str(value))
    new_key = ident.DmCode.from_element(code).dmc_string()
    issue = params.get("issue_info")
    if issue:
        info = xio.find(el, "dmRefIdent/issueInfo")
        if info is None:
            info = etree.Element("issueInfo")
            code.addnext(info)
        for name in ("issueNumber", "inWork"):
            if name in issue:
                info.set(name, str(issue[name]))
    href = el.get(XLINK_HREF)
    if href and old_key in href:
        el.set(XLINK_HREF, href.replace(old_key, new_key))


def _update_internal_ref(tree: Any, el: Any, params: dict[str, Any]) -> None:
    (target,) = require(params, "internal_ref_id")
    by_id(tree, str(target))  # the new target must exist in the data module
    el.set("internalRefId", str(target))
    if params.get("target_type"):
        el.set("internalRefTargetType", str(params["target_type"]))


def update_ref(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Retarget the reference the zone designates.

    * ``dmRef``: ``dm_code`` (dict of the dmCode attributes to change, for instance
      ``{"infoCode": "520"}``) and optionally ``issue_info`` (``issueNumber`` / ``inWork``); a
      ``xlink:href`` that contains the old code is updated too.
    * ``internalRef``: ``internal_ref_id`` (an id that exists in the data module) and
      optionally ``target_type``.

    The only values written are the ones given in ``params``.
    """
    el = target_of(tree, zone)
    before = xml_of(el)
    if el.tag == "dmRef":
        _update_dm_ref(el, params)
    elif el.tag == "internalRef":
        _update_internal_ref(tree, el, params)
    else:
        raise OpError(f"update_ref applies to dmRef or internalRef, not {el.tag}")
    after = xml_of(el)
    if after == before:
        raise OpError("the reference already points there")
    return OpResult(path_of(el), "modify", before, after)
