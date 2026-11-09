"""remove_requirement: designate a requirement to delete (the deletion is a mark, added later)."""

from __future__ import annotations

from typing import Any

from redactech.models import Zone
from redactech.s1000d import io as xio
from redactech.s1000d.ops._common import OpError, OpResult, path_of, xml_of
from redactech.s1000d.ops.add_requirement import preliminary_requirements, requirement_spec


def remove_requirement(tree: Any, zone: Zone | None, params: dict[str, Any]) -> OpResult:
    """Return the requirement identified by ``id`` or ``part_number`` with ``change_type="delete"``.

    ``requirement`` gives the kind (spare | supply | tool | supportEquipment). The tree is NOT
    changed; exactly one descriptor must match.
    """
    container_tag, _group, descr_tag, _none, _prefix = requirement_spec(params)
    wanted_id, part_number = params.get("id"), params.get("part_number")
    if not wanted_id and not part_number:
        raise OpError("missing parameter(s): id or part_number")
    container = preliminary_requirements(tree).find(container_tag)
    if container is None:
        raise OpError(f"preliminaryRqmts has no {container_tag}")
    matches = []
    for descr in container.iter(descr_tag):
        numbers = {"".join(n.itertext()).strip() for n in xio.findall(descr, ".//partNumber")}
        if (wanted_id and descr.get("id") == wanted_id) or (
            part_number and str(part_number) in numbers
        ):
            matches.append(descr)
    if len(matches) != 1:
        raise OpError(f"expected one matching {descr_tag}, found {len(matches)}")
    xml = xml_of(matches[0])
    return OpResult(path_of(matches[0]), "delete", xml, xml)
