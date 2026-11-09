"""Tests of redactech.s1000d.trace (reasons, change marks, consolidation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.s1000d import io as xio
from redactech.s1000d import trace
from redactech.s1000d.ops._common import xml_of

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"


def load(name: str) -> xio.XmlDoc:
    return xio.load(FIXTURES / name)


def find(doc: xio.XmlDoc, expr: str):
    return xio.xpath(doc.root, expr)[0]


def status_tags(doc: xio.XmlDoc) -> list[str]:
    return [c.tag for c in find(doc, "//dmStatus")]


# --- ensure_reason ------------------------------------------------------------


def test_reason_is_added_after_quality_assurance_with_the_layout_of_the_file():
    doc = load(PROCED)
    assert trace.ensure_reason(doc, "Part replaced") == "rfu-0001"
    assert status_tags(doc)[-2:] == ["qualityAssurance", "reasonForUpdate"]
    reason = find(doc, "//reasonForUpdate")
    assert reason.get("id") == "rfu-0001" and reason.find("simplePara").text == "Part replaced"
    assert xml_of(find(doc, "//dmStatus")).endswith(
        "</qualityAssurance>\n      <reasonForUpdate id=\"rfu-0001\">\n"
        "        <simplePara>Part replaced</simplePara>\n"
        "      </reasonForUpdate>\n    </dmStatus>"
    )


def test_an_identical_reason_is_reused_and_a_new_one_gets_the_next_id():
    doc = load(PROCED)
    first = trace.ensure_reason(doc, "Part replaced")
    assert trace.ensure_reason(doc, "  Part   replaced ") == first
    assert trace.ensure_reason(doc, "Step added") == "rfu-0002"
    assert [r.get("id") for r in doc.root.iter("reasonForUpdate")] == ["rfu-0001", "rfu-0002"]


def test_reasons_of_a_marked_data_module():
    doc = load(MARKED)
    assert trace.ensure_reason(doc, "Step modified.") == "rfu-0002"  # existing text
    assert trace.ensure_reason(doc, "Something else") == "rfu-0004"
    ids = [r.get("id") for r in doc.root.iter("reasonForUpdate")]
    assert ids == ["rfu-0001", "rfu-0002", "rfu-0003", "rfu-0004"]


def test_reason_goes_before_product_safety_and_remarks():
    xml = (
        b"<dmodule><identAndStatusSection><dmStatus><security/><qualityAssurance/>"
        b"<remarks/></dmStatus></identAndStatusSection></dmodule>"
    )
    doc = xio.load_bytes(xml)
    trace.ensure_reason(doc, "x")
    assert status_tags(doc) == ["security", "qualityAssurance", "reasonForUpdate", "remarks"]
    bare = xio.load_bytes(
        b"<dmodule><identAndStatusSection><dmStatus><remarks/></dmStatus>"
        b"</identAndStatusSection></dmodule>"
    )
    trace.ensure_reason(bare, "x")
    assert status_tags(bare) == ["reasonForUpdate", "remarks"]


def test_reason_errors():
    with pytest.raises(trace.TraceError):
        trace.ensure_reason(xio.load_bytes(b"<dmodule/>"), "x")
    with pytest.raises(trace.TraceError):
        trace.ensure_reason(load(PROCED), "   ")


# --- mark ---------------------------------------------------------------------


def test_mark_sets_the_change_attributes():
    doc = load(PROCED)
    step = find(doc, "//proceduralStep[@id='stp-0001']")
    assert trace.mark(step, "modify", "rfu-0001") is step
    assert (step.get("changeMark"), step.get("changeType")) == ("1", "modify")
    assert step.get("reasonForUpdateRefIds") == "rfu-0001"


def test_reason_ids_accumulate_without_duplicates():
    doc = load(PROCED)
    step = find(doc, "//proceduralStep[@id='stp-0001']")
    for rfu in ("rfu-0001", "rfu-0002", "rfu-0001"):
        trace.mark(step, "modify", rfu)
    assert step.get("reasonForUpdateRefIds") == "rfu-0001 rfu-0002"
    trace.mark(step, "modify", None)
    assert step.get("reasonForUpdateRefIds") == "rfu-0001 rfu-0002"


@pytest.mark.parametrize(
    "sequence,expected",
    [
        (["add", "modify"], "add"),
        (["modify", "delete"], "delete"),
        (["delete", "modify"], "delete"),
        (["modify", "modify"], "modify"),
        (["modify", "add"], "add"),
    ],
)
def test_change_type_precedence(sequence: list[str], expected: str):
    doc = load(PROCED)
    step = find(doc, "//proceduralStep[@id='stp-0002']")
    for change in sequence:
        trace.mark(step, change, "rfu-0001")
    assert step.get("changeType") == expected


def test_mark_without_change_attributes_goes_to_the_nearest_ancestor():
    doc = load(PROCED)
    reference = find(doc, "//internalRef[@internalRefTargetType='irtt05']")
    marked = trace.mark(reference, "modify", "rfu-0001")
    assert marked.tag == "para" and marked is reference.getparent()
    assert "changeMark" not in reference.attrib
    code = find(doc, "//brexDmRef/dmRef/dmRefIdent/dmCode")
    assert trace.mark(code, "modify", "rfu-0001").tag == "dmRef"
    inline = xio.load_bytes(b"<r><para>a <emphasis>b</emphasis></para></r>")
    assert trace.mark(inline.root.find(".//emphasis"), "add", "x").tag == "para"


def test_mark_errors():
    doc = load(PROCED)
    step = find(doc, "//proceduralStep[@id='stp-0001']")
    with pytest.raises(trace.TraceError):
        trace.mark(step, "erase", "rfu-0001")
    lone = xio.load_bytes(b"<issueInfo/>")
    with pytest.raises(trace.TraceError):
        trace.mark(lone.root, "add", "rfu-0001")


# --- consolidate --------------------------------------------------------------


def test_consolidation_removes_deleted_elements_marks_and_reasons():
    doc = load(MARKED)
    assert [e.get("id") for e in doc.root.iter("proceduralStep")][-1] == "stp-0004"
    assert trace.consolidate(doc) == (1, 3)
    assert [e.get("id") for e in doc.root.iter("proceduralStep")] == [
        "stp-0001",
        "stp-0002",
        "stp-0003",
    ]
    for element in doc.root.iter():
        if isinstance(element.tag, str):
            for name in trace.CHANGE_ATTRIBUTES:
                assert name not in element.attrib
    assert list(doc.root.iter("reasonForUpdate")) == []


def test_consolidation_keeps_the_layout_tidy():
    doc = load(MARKED)
    trace.consolidate(doc)
    procedure = xml_of(find(doc, "//mainProcedure"))
    assert procedure.endswith("</proceduralStep>\n      </mainProcedure>")
    assert "\n\n" not in procedure
    assert xml_of(find(doc, "//dmStatus")).endswith("</qualityAssurance>\n    </dmStatus>")


def test_consolidation_removes_only_the_outermost_deleted_element():
    doc = xio.load_bytes(
        b'<r><a changeType="delete"><b changeType="delete"/></a>'
        b'<c changeMark="1" changeType="add" reasonForUpdateRefIds="x"/></r>'
    )
    assert trace.consolidate(doc) == (1, 0)
    assert xml_of(doc.root) == "<r><c/></r>"


def test_consolidating_an_unmarked_document_changes_nothing():
    doc = load(PROCED)
    assert trace.consolidate(doc) == (0, 0)
    assert xio.dumps(doc) == doc.raw
