"""Tests of redactech.s1000d.ops (pure operations on a tree copy)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from redactech.models import SourceRef, Zone
from redactech.s1000d import diff, ops, validate
from redactech.s1000d import io as xio
from redactech.s1000d.ops import OpError
from redactech.s1000d.ops._common import xml_of

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
VIOLATING = f"DMC-RTPROTO-{CODE}-521A-A_001-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
COMREP = f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
APPLIC = f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML"
STEP_INDENT = "\n        "  # indentation of the steps in the fixtures


def zone(xpath: str = "", element_id: str | None = None) -> Zone:
    return Zone(
        id="z1",
        ref=SourceRef(source_id="fixtures", doc_key="doc"),
        xpath=xpath,
        element_id=element_id,
        certainty="certain",
        found_by="code",
        reason="test",
        operation_id="op1",
    )


def load(name: str) -> xio.XmlDoc:
    return xio.load(FIXTURES / name)


def path_to(doc: xio.XmlDoc, expr: str) -> str:
    element = xio.xpath(doc.root, expr)[0]
    return element.getroottree().getpath(element)


def run(name: str, kind: str, z: Zone | None, params: dict[str, Any]):
    """Apply an operation to a copy of a fixture: (original doc, edited tree, result)."""
    doc = load(name)
    tree = ops.copy_tree(doc.tree)
    result = ops.apply(tree, kind, z, params)
    assert xio.dumps(doc) == doc.raw  # the original document was not touched
    return doc, tree, result


def values(tree: Any) -> set[str]:
    """Every attribute value and stripped text of a tree (to check what a change introduced)."""
    found: set[str] = set()
    for el in xio.root_of(tree).iter():
        if not isinstance(el.tag, str):
            continue
        found.update(v for v in el.attrib.values())
        for text in (el.text, el.tail):
            if text and text.strip():
                found.add(text.strip())
    return found


def step_ids(tree: Any) -> list[str]:
    return [e.get("id") for e in xio.root_of(tree).iter("proceduralStep")]


def main_procedure_xml(tree: Any) -> str:
    element = xio.root_of(tree).find(".//mainProcedure")
    return xml_of(element)  # standalone: no inherited namespace declarations


def assert_ids_unique(tree: Any) -> None:
    assert all(r.ok for r in validate.check_ids(tree))


def test_xml_of_is_standalone_without_inherited_namespace_declarations():
    doc = load(PROCED)
    para = doc.root.find(".//para")
    text = xml_of(para)
    assert text.startswith("<para>") and "xmlns:" not in text
    dm_ref = xml_of(doc.root.find(".//brexDmRef/dmRef"))  # keeps the declaration it really uses
    assert 'xmlns:xlink="http://www.w3.org/1999/xlink"' in dm_ref and "xmlns:xsi" not in dm_ref
    assert "xmlns:" not in xml_of(doc.root.find(".//mainProcedure"))
    assert not xml_of(para).endswith("\n")  # no tail
    assert xio.dumps(doc) == doc.raw  # the document was not touched


# --- replace_part -------------------------------------------------------------


def test_replace_part_in_an_ipd_reference():
    doc = load(IPD)
    z = zone(path_to(doc, "//partRef[@partNumberValue='LRU1010']"))
    before_doc, tree, result = run(IPD, "replace_part", z, {"old": "LRU1010", "new": "LRU2020"})
    assert result.change_type == "modify"
    assert 'partNumberValue="LRU1010"' in result.before_xml
    assert 'partNumberValue="LRU2020"' in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]
    assert values(tree) - values(before_doc.tree) == {"LRU2020"}  # veracity: only the new value
    assert_ids_unique(tree)


def test_replace_part_in_a_comrep_declaration():
    doc = load(COMREP)
    z = zone(path_to(doc, "//partSpec/partIdent[@partNumberValue='LRU1010']"))
    before_doc, tree, result = run(COMREP, "replace_part", z, {"old": "LRU1010", "new": "LRU2020"})
    assert 'partNumberValue="LRU2020"' in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]
    assert values(tree) - values(before_doc.tree) == {"LRU2020"}


def test_replace_part_in_a_part_number_text():
    doc = load(PROCED)
    z = zone(path_to(doc, "//spareDescr//partNumber"))
    before_doc, tree, result = run(PROCED, "replace_part", z, {"old": "X2", "new": "X3"})
    assert "<partNumber>X3</partNumber>" in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]
    assert values(tree) - values(before_doc.tree) == {"X3"}


def test_replace_part_in_free_text_keeps_the_rest_of_the_paragraph():
    doc = load(APPLIC)
    z = zone(path_to(doc, "//para[contains(., 'LRU1010')]"))
    before_doc, tree, result = run(APPLIC, "replace_part", z, {"old": "LRU1010", "new": "LRU2020"})
    assert result.after_xml == (
        "<para>The LRU2020 housing is common to product A and product B.</para>"
    )
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]


def test_free_text_replacement_is_whole_word_and_can_target_one_mention():
    def edit(params: dict[str, Any]) -> str:
        document = xio.load_bytes(b"<r><p>LRU1010 and LRU10100 and LRU1010-A and LRU1010.</p></r>")
        ops.replace_part(document.tree, zone("/r/p"), {"old": "LRU1010", "new": "Z1", **params})
        return document.root.find("p").text

    assert edit({}) == "Z1 and LRU10100 and LRU1010-A and Z1."
    assert edit({"occurrence": 1}) == "Z1 and LRU10100 and LRU1010-A and LRU1010."
    assert edit({"occurrence": -1}) == "LRU1010 and LRU10100 and LRU1010-A and Z1."


def test_free_text_replacement_covers_text_around_inline_children():
    document = xio.load_bytes(b"<r><p>LRU1010 <b>LRU1010</b> then LRU1010</p></r>")
    ops.replace_part(document.tree, zone("/r/p"), {"old": "LRU1010", "new": "Z1"})
    assert etree.tostring(document.root.find("p"), encoding="unicode") == (
        "<p>Z1 <b>LRU1010</b> then Z1</p>"  # the child element has its own zone
    )


@pytest.mark.parametrize(
    "xpath,params",
    [
        ("//partRef", {"old": "NOPE", "new": "X"}),
        ("//partRef", {"old": "LRU1010"}),
        ("//partRef", {"new": "X"}),
        ("//doesNotExist", {"old": "LRU1010", "new": "X"}),
    ],
)
def test_replace_part_refuses_what_it_cannot_do(xpath: str, params: dict[str, Any]):
    with pytest.raises(OpError):
        run(IPD, "replace_part", zone(xpath), params)


def test_replace_part_needs_a_zone():
    with pytest.raises(OpError):
        run(IPD, "replace_part", None, {"old": "LRU1010", "new": "X"})


# --- replace_text -------------------------------------------------------------


def test_replace_text_below_a_step():
    z = zone(element_id="stp-0003")
    before_doc, tree, result = run(
        PROCED, "replace_text", z, {"old": "by hand", "new": "with the wrench"}
    )
    assert "Tighten the fasteners with the wrench." in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == [
        "/dmodule/content/procedure/mainProcedure/proceduralStep[3]/para"
    ]
    assert values(tree) - values(before_doc.tree) == {"Tighten the fasteners with the wrench."}


def test_replace_text_scope_and_whole_word():
    z = zone(element_id="stp-0003")
    with pytest.raises(OpError):  # own text of the step itself is only whitespace
        run(PROCED, "replace_text", z, {"old": "hand", "new": "x", "scope": "element"})
    with pytest.raises(OpError):
        run(PROCED, "replace_text", z, {"old": "fast", "new": "x", "whole_word": True})
    _, _, result = run(PROCED, "replace_text", z, {"old": "fast", "new": "FAST"})
    assert "FASTeners" in result.after_xml
    with pytest.raises(OpError):
        run(PROCED, "replace_text", z, {"old": "hand", "new": "x", "scope": "everywhere"})


# --- insert_step --------------------------------------------------------------


def test_insert_step_after_a_step():
    before_doc, tree, result = run(
        PROCED, "insert_step", zone(), {"after_id": "stp-0002", "para": "Check the torque."}
    )
    assert step_ids(tree) == [
        "stp-0001", "stp-0002", "stp-0006", "stp-0003", "stp-0004", "stp-0005",
    ]
    assert result.change_type == "add" and result.before_xml == ""
    new_step = (
        '<proceduralStep id="stp-0006">\n          <para>Check the torque.</para>\n'
        "        </proceduralStep>"
    )
    assert result.after_xml == new_step
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]
    assert values(tree) - values(before_doc.tree) == {"stp-0006", "Check the torque."}
    assert_ids_unique(tree)
    xml = main_procedure_xml(tree)
    expected = (
        f"</proceduralStep>{STEP_INDENT}{new_step}{STEP_INDENT}"
        '<proceduralStep id="stp-0003">'
    )
    assert expected in xml


def test_insert_step_before_first_and_after_last_keep_the_layout():
    _, tree, _ = run(PROCED, "insert_step", zone(), {"before_id": "stp-0001", "para": "First."})
    assert step_ids(tree)[0] == "stp-0006"
    assert f'<mainProcedure>{STEP_INDENT}<proceduralStep id="stp-0006">' in main_procedure_xml(tree)
    _, tree, _ = run(PROCED, "insert_step", zone(), {"after_id": "stp-0005", "para": "Last."})
    xml = main_procedure_xml(tree)
    assert step_ids(tree)[-1] == "stp-0006"
    assert xml.endswith("</proceduralStep>\n      </mainProcedure>")
    assert "\n\n" not in xml


def test_insert_step_uses_the_zone_element_and_compact_xml():
    _, tree, result = run(PROCED, "insert_step", zone(element_id="stp-0001"), {"para": "Next."})
    assert step_ids(tree)[:2] == ["stp-0001", "stp-0006"] and result.change_type == "add"
    compact = xio.load_bytes(
        b'<r><proceduralStep id="stp-0001"><para>a</para></proceduralStep></r>'
    )
    ops.insert_step(compact.tree, zone(), {"after_id": "stp-0001", "para": "b"})
    assert etree.tostring(compact.root, encoding="unicode") == (
        '<r><proceduralStep id="stp-0001"><para>a</para></proceduralStep>'
        '<proceduralStep id="stp-0002"><para>b</para></proceduralStep></r>'
    )


@pytest.mark.parametrize(
    "params",
    [
        {"para": "x"},
        {"after_id": "stp-0001", "before_id": "stp-0002", "para": "x"},
        {"after_id": "ghost", "para": "x"},
        {"after_id": "tool-0001", "para": "x"},
        {"after_id": "stp-0001"},
    ],
)
def test_insert_step_refuses_bad_parameters(params: dict[str, Any]):
    with pytest.raises(OpError):
        run(PROCED, "insert_step", zone(), params)


# --- delete_step --------------------------------------------------------------


def test_delete_step_designates_without_removing():
    before_doc, tree, result = run(PROCED, "delete_step", zone(), {"step_id": "stp-0003"})
    assert result.change_type == "delete"
    assert result.element_xpath == "/dmodule/content/procedure/mainProcedure/proceduralStep[3]"
    assert result.before_xml == result.after_xml and 'id="stp-0003"' in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == []
    assert step_ids(tree) == step_ids(before_doc.tree)


def test_delete_step_from_the_zone_and_errors():
    _, _, result = run(PROCED, "delete_step", zone(element_id="stp-0002"), {})
    assert 'id="stp-0002"' in result.before_xml
    for params in ({}, {"step_id": "ghost"}, {"step_id": "tool-0001"}):
        with pytest.raises(OpError):
            run(PROCED, "delete_step", zone(), params)


# --- move_step ----------------------------------------------------------------


def test_move_step_after_another():
    before_doc, tree, result = run(
        PROCED, "move_step", zone(), {"step_id": "stp-0005", "after_id": "stp-0001"}
    )
    assert step_ids(tree) == ["stp-0001", "stp-0005", "stp-0002", "stp-0003", "stp-0004"]
    assert result.change_type == "modify" and result.before_xml != result.after_xml
    assert result.element_xpath.endswith("proceduralStep[2]")
    assert diff.changed_elements(before_doc.tree, tree) == [
        "/dmodule/content/procedure/mainProcedure"
    ]
    assert set(step_ids(tree)) == set(step_ids(before_doc.tree))
    assert values(tree) == values(before_doc.tree)  # nothing new is written


def test_move_step_keeps_the_layout_at_both_ends():
    _, tree, _ = run(PROCED, "move_step", zone(), {"step_id": "stp-0001", "after_id": "stp-0005"})
    xml = main_procedure_xml(tree)
    assert step_ids(tree) == ["stp-0002", "stp-0003", "stp-0004", "stp-0005", "stp-0001"]
    assert xml.endswith("</proceduralStep>\n      </mainProcedure>") and "\n\n" not in xml
    _, tree, _ = run(PROCED, "move_step", zone(), {"step_id": "stp-0005", "before_id": "stp-0001"})
    xml = main_procedure_xml(tree)
    assert step_ids(tree) == ["stp-0005", "stp-0001", "stp-0002", "stp-0003", "stp-0004"]
    assert xml.endswith("</proceduralStep>\n      </mainProcedure>") and "\n\n" not in xml
    assert f'<mainProcedure>{STEP_INDENT}<proceduralStep id="stp-0005">' in xml


@pytest.mark.parametrize(
    "params",
    [
        {"step_id": "stp-0002", "after_id": "stp-0002"},
        {"step_id": "stp-0002"},
        {"step_id": "ghost", "after_id": "stp-0001"},
        {"step_id": "stp-0002", "after_id": "ghost"},
    ],
)
def test_move_step_refuses_bad_parameters(params: dict[str, Any]):
    with pytest.raises(OpError):
        run(PROCED, "move_step", zone(), params)


def test_move_step_cannot_enter_its_own_subtree():
    document = xio.load_bytes(
        b'<r><proceduralStep id="a"><proceduralStep id="b"/></proceduralStep></r>'
    )
    with pytest.raises(OpError):
        ops.move_step(document.tree, zone(), {"step_id": "a", "after_id": "b"})


# --- update_ref ---------------------------------------------------------------


def test_update_dm_ref_attributes():
    doc = load(PROCED)
    z = zone(path_to(doc, "//brexDmRef/dmRef"))
    before_doc, tree, result = run(
        PROCED, "update_ref", z, {"dm_code": {"modelIdentCode": "RTDEFLT"}}
    )
    assert 'modelIdentCode="RTDEFLT"' in result.after_xml and result.change_type == "modify"
    assert diff.changed_elements(before_doc.tree, tree) == [
        result.element_xpath + "/dmRefIdent/dmCode"
    ]
    assert values(tree) - values(before_doc.tree) == {"RTDEFLT"}


DM_REF = (
    b'<r xmlns:xlink="http://www.w3.org/1999/xlink"><dmRef xlink:type="simple" '
    b'xlink:href="URN:S1000D:DMC-MODEL-AAA-D00-00-00-00AA-040A-A_001-00"><dmRefIdent>'
    b'<dmCode modelIdentCode="MODEL" systemDiffCode="AAA" systemCode="D00" subSystemCode="0" '
    b'subSubSystemCode="0" assyCode="00" disassyCode="00" disassyCodeVariant="AA" '
    b'infoCode="040" infoCodeVariant="A" itemLocationCode="A"/>'
    b'<issueInfo issueNumber="001" inWork="00"/></dmRefIdent></dmRef></r>'
)


def test_update_dm_ref_also_updates_href_and_issue_info():
    document = xio.load_bytes(DM_REF)
    ops.update_ref(
        document.tree,
        zone("//dmRef"),
        {"dm_code": {"infoCode": "520"}, "issue_info": {"issueNumber": "002"}},
    )
    xml = etree.tostring(document.root, encoding="unicode")
    assert "DMC-MODEL-AAA-D00-00-00-00AA-520A-A_001-00" in xml
    assert 'infoCode="520"' in xml and 'issueNumber="002"' in xml and 'inWork="00"' in xml


def test_update_internal_ref_to_an_existing_id():
    doc = load(PROCED)
    z = zone(path_to(doc, "//internalRef[@internalRefTargetType='irtt05']"))
    before_doc, tree, result = run(PROCED, "update_ref", z, {"internal_ref_id": "sup-0001"})
    assert 'internalRefId="sup-0001"' in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]


@pytest.mark.parametrize(
    "expr,params",
    [
        ("//internalRef", {"internal_ref_id": "ghost"}),
        ("//internalRef[@internalRefId='tool-0001']", {"internal_ref_id": "tool-0001"}),
        ("//internalRef", {}),
        ("//brexDmRef/dmRef", {"dm_code": {"nonsense": "x"}}),
        ("//brexDmRef/dmRef", {}),
        ("//para", {"internal_ref_id": "tool-0001"}),
    ],
)
def test_update_ref_refuses_bad_requests(expr: str, params: dict[str, Any]):
    doc = load(PROCED)
    with pytest.raises(OpError):
        run(PROCED, "update_ref", zone(path_to(doc, expr)), params)


# --- add_requirement ----------------------------------------------------------

SPARE = {
    "requirement": "spare",
    "part_number": "Y9",
    "manufacturer_code": "FAKE1",
    "quantity": 2,
    "name": "Plate",
}


def test_add_a_spare_after_the_existing_ones():
    before_doc, tree, result = run(PROCED, "add_requirement", zone(), SPARE)
    assert result.change_type == "add" and result.before_xml == ""
    assert 'id="spr-0002"' in result.after_xml
    for fragment in ("<name>Plate</name>", "<manufacturerCode>FAKE1</manufacturerCode>"):
        assert fragment in result.after_xml
    assert "<partNumber>Y9</partNumber>" in result.after_xml
    assert "<reqQuantity>2</reqQuantity>" in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == [result.element_xpath]
    introduced = values(tree) - values(before_doc.tree)
    assert {"spr-0002", "Plate", "Y9"} <= introduced  # veracity: only given values or the new id
    assert introduced <= {"spr-0002", "Plate", "Y9", "2", "FAKE1"}
    assert_ids_unique(tree)
    group = xml_of(xio.root_of(tree).find(".//spareDescrGroup"))
    layout = (
        '</spareDescr>\n            <spareDescr id="spr-0002">\n'
        "              <name>Plate</name>"
    )
    assert layout in group


def test_add_a_requirement_replaces_the_none_placeholder():
    _, tree, result = run(VIOLATING, "add_requirement", zone(), SPARE)
    assert xio.root_of(tree).find(".//reqSpares/noSpares") is None
    assert xio.root_of(tree).find(".//reqSpares/spareDescrGroup/spareDescr") is not None
    assert 'id="spr-0001"' in result.after_xml


@pytest.mark.parametrize(
    "kind,tag,id_",
    [
        ("supply", "supplyDescr", "sup-0002"),
        ("tool", "supportEquipDescr", "tool-0002"),
        ("supportEquipment", "supportEquipDescr", "tool-0002"),
    ],
)
def test_add_other_requirement_kinds(kind: str, tag: str, id_: str):
    _, _, result = run(PROCED, "add_requirement", zone(), {**SPARE, "requirement": kind})
    assert result.after_xml.startswith(f'<{tag} id="{id_}">')


@pytest.mark.parametrize(
    "change",
    [
        {"manufacturer_code": None},
        {"part_number": None},
        {"quantity": None},
        {"requirement": "gadget"},
        {"requirement": None},
    ],
)
def test_add_requirement_refuses_missing_values(change: dict[str, Any]):
    with pytest.raises(OpError):
        run(PROCED, "add_requirement", zone(), {**SPARE, **change})


def test_add_requirement_needs_preliminary_requirements():
    with pytest.raises(OpError):
        run(IPD, "add_requirement", zone(), SPARE)


# --- remove_requirement -------------------------------------------------------


def test_remove_requirement_designates_without_removing():
    params = {"requirement": "spare", "part_number": "X2"}
    before_doc, tree, result = run(PROCED, "remove_requirement", zone(), params)
    assert result.change_type == "delete" and result.element_xpath.endswith("/spareDescr")
    assert result.before_xml == result.after_xml and "X2" in result.after_xml
    assert diff.changed_elements(before_doc.tree, tree) == []
    _, _, by_id_result = run(
        PROCED, "remove_requirement", zone(), {"requirement": "supply", "id": "sup-0001"}
    )
    assert 'id="sup-0001"' in by_id_result.before_xml


@pytest.mark.parametrize(
    "params",
    [
        {"requirement": "spare", "part_number": "NOPE"},
        {"requirement": "spare"},
        {"requirement": "gadget", "part_number": "X2"},
    ],
)
def test_remove_requirement_refuses_unknown_or_missing(params: dict[str, Any]):
    with pytest.raises(OpError):
        run(PROCED, "remove_requirement", zone(), params)


def test_remove_requirement_refuses_an_ambiguous_match():
    document = xio.load_bytes(
        b"<r><preliminaryRqmts><reqSpares><spareDescrGroup>"
        b"<spareDescr><identNumber><partAndSerialNumber><partNumber>P</partNumber>"
        b"</partAndSerialNumber></identNumber></spareDescr>"
        b"<spareDescr><identNumber><partAndSerialNumber><partNumber>P</partNumber>"
        b"</partAndSerialNumber></identNumber></spareDescr>"
        b"</spareDescrGroup></reqSpares></preliminaryRqmts></r>"
    )
    with pytest.raises(OpError):
        ops.remove_requirement(document.tree, zone(), {"requirement": "spare", "part_number": "P"})


# --- registry -----------------------------------------------------------------


def test_registry_covers_the_eight_operations():
    assert set(ops.OPS) == {
        "replace_part",
        "replace_text",
        "insert_step",
        "delete_step",
        "move_step",
        "update_ref",
        "add_requirement",
        "remove_requirement",
    }
    with pytest.raises(OpError):
        ops.apply(load(PROCED).tree, "translate_dm", None, {})


def test_operations_accept_a_root_element_too():
    document = xio.load_bytes(b"<r><p>LRU1010</p></r>")
    ops.replace_part(document.root, zone("/r/p"), {"old": "LRU1010", "new": "Z"})
    assert document.root.find("p").text == "Z"
