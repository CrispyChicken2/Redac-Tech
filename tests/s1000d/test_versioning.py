"""Tests of redactech.s1000d.versioning (policies, suggestion)."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from redactech.config import TraceConfig
from redactech.models import Operation, SourceSpan, Target
from redactech.s1000d import io as xio
from redactech.s1000d import versioning as vs

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
TODAY = datetime.date(2025, 3, 7)


def load(name: str) -> xio.XmlDoc:
    return xio.load(FIXTURES / name)


def issue(doc: xio.XmlDoc) -> tuple[str, str]:
    info = xio.xpath(doc.root, "//dmIdent/issueInfo")[0]
    return info.get("issueNumber"), info.get("inWork")


def date_of(doc: xio.XmlDoc) -> tuple[str, str, str]:
    date = xio.xpath(doc.root, "//dmAddressItems/issueDate")[0]
    return date.get("year"), date.get("month"), date.get("day")


def issue_type(doc: xio.XmlDoc) -> str:
    return xio.xpath(doc.root, "//dmStatus")[0].get("issueType")


# --- apply_policy -------------------------------------------------------------


def test_policy_none_changes_nothing():
    doc = load(PROCED)
    assert vs.apply_policy(doc, "none", TODAY) == PROCED
    assert xio.dumps(doc) == doc.raw


def test_in_work_increments_the_in_work_number_and_dates_the_module():
    doc = load(PROCED)
    assert vs.apply_policy(doc, "in_work", TODAY) == PROCED.replace("001-00", "001-01")
    assert issue(doc) == ("001", "01")
    assert date_of(doc) == ("2025", "03", "07")
    assert issue_type(doc) == "new"  # kept on issue 001


def test_in_work_on_a_later_issue_marks_the_module_as_changed():
    doc = load(MARKED)
    assert vs.apply_policy(doc, "in_work", TODAY) == MARKED.replace("007-00", "007-01")
    assert issue(doc) == ("007", "01") and issue_type(doc) == "changed"
    assert len(list(doc.root.iter("reasonForUpdate"))) == 3  # in-work marks are kept


def test_new_issue_consolidates_first_then_increments_the_issue():
    doc = load(MARKED)
    assert vs.apply_policy(doc, "new_issue", TODAY) == MARKED.replace("007-00", "008-00")
    assert issue(doc) == ("008", "00") and date_of(doc) == ("2025", "03", "07")
    assert [e.get("id") for e in doc.root.iter("proceduralStep")] == [
        "stp-0001",
        "stp-0002",
        "stp-0003",
    ]
    assert list(doc.root.iter("reasonForUpdate")) == []
    assert all("changeMark" not in e.attrib for e in doc.root.iter() if isinstance(e.tag, str))


def test_new_issue_from_001_becomes_changed():
    doc = load(PROCED)
    assert vs.apply_policy(doc, "new_issue", TODAY) == PROCED.replace("001-00", "002-00")
    assert issue(doc) == ("002", "00") and issue_type(doc) == "changed"


def test_consolidation_can_be_switched_off():
    config = TraceConfig(consolidate_on_new_issue=False)
    doc = load(MARKED)
    vs.apply_policy(doc, "new_issue", TODAY, config)
    assert len(list(doc.root.iter("proceduralStep"))) == 4
    other = load(MARKED)
    vs.apply_policy(other, "new_issue", TODAY, consolidate=False)
    assert len(list(other.root.iter("proceduralStep"))) == 4


def test_today_defaults_to_the_current_date():
    doc = load(PROCED)
    vs.apply_policy(doc, "in_work")
    today = datetime.date.today()
    assert date_of(doc) == (f"{today.year:04d}", f"{today.month:02d}", f"{today.day:02d}")


def test_in_work_carries_over_and_stops_at_99():
    doc = load(PROCED)
    xio.xpath(doc.root, "//dmIdent/issueInfo")[0].set("inWork", "09")
    assert vs.apply_policy(doc, "in_work", TODAY).endswith("_001-10_EN-US.XML")
    xio.xpath(doc.root, "//dmIdent/issueInfo")[0].set("inWork", "99")
    with pytest.raises(vs.VersioningError):
        vs.apply_policy(doc, "in_work", TODAY)


def test_file_name_follows_the_case_style_of_the_current_file():
    raw = (FIXTURES / PROCED).read_bytes()
    named = Path(PROCED.replace("EN-US", "en-US").replace(".XML", ".xml"))
    doc = xio.load_bytes(raw, named)
    assert vs.apply_policy(doc, "in_work", TODAY) == named.name.replace("001-00", "001-01")


@pytest.mark.parametrize(
    "xml,mode",
    [
        (b"<dmodule/>", "in_work"),
        (b"<dmodule><identAndStatusSection><dmAddress><dmIdent><issueInfo issueNumber='a' "
         b"inWork='00'/></dmIdent></dmAddress></identAndStatusSection></dmodule>", "new_issue"),
    ],
)
def test_data_modules_without_usable_issue_info_are_refused(xml: bytes, mode: str):
    with pytest.raises(vs.VersioningError):
        vs.apply_policy(xio.load_bytes(xml), mode, TODAY)


def test_unknown_mode_is_refused():
    with pytest.raises(vs.VersioningError):
        vs.apply_policy(load(PROCED), "sometimes", TODAY)


# --- suggest_policy -----------------------------------------------------------


def op(kind: str, params: dict | None = None, op_id: str = "op-1") -> Operation:
    return Operation(
        id=op_id,
        kind=kind,
        target=Target(),
        params=params or {},
        rationale="r",
        source=[SourceSpan(doc="m", quote="q")],
    )


@pytest.mark.parametrize(
    "operation,expected",
    [
        (op("update_ref"), "in_work"),
        (op("replace_text", {"old": "colour", "new": "color"}), "in_work"),
        (op("replace_text", {"old": "12 Nm", "new": "15 Nm"}), "new_issue"),
        (op("replace_text", {"old": "12,5", "new": "15"}), "new_issue"),
        (op("replace_part", {"old": "A", "new": "B"}), "in_work"),
        (op("replace_part", {"old": "A", "new": "B", "requirement": "spare"}), "new_issue"),
        (op("replace_part", {"old": "A", "new": "B", "requirement": "tool"}), "in_work"),
        (op("add_requirement", {"requirement": "spare"}), "new_issue"),
        (op("add_requirement", {"requirement": "supply"}), "new_issue"),
        (op("remove_requirement", {"requirement": "tool"}), "in_work"),
        (op("insert_step", {"para": "x", "after_id": "a"}), "in_work"),
        (op("insert_step", {"para": "x", "after_id": "a", "warning": "Hot"}), "new_issue"),
        (op("insert_step", {"para": "x", "after_id": "a", "caution": "Sharp"}), "new_issue"),
        (op("move_step"), "in_work"),
    ],
)
def test_single_operation_suggestions(operation: Operation, expected: str):
    policy = vs.suggest_policy([operation])
    assert (policy.suggested, policy.mode) == (expected, expected)
    assert policy.per_doc == {} and len(policy.reasons) == 1 and operation.id in policy.reasons[0]


def test_more_than_three_steps_inserted_or_deleted_need_a_new_issue():
    three = [op("insert_step", op_id=f"op-{n}") for n in range(3)]
    assert vs.suggest_policy(three).suggested == "in_work"
    four = [*three, op("delete_step", op_id="op-9")]
    policy = vs.suggest_policy(four)
    assert policy.suggested == "new_issue"
    assert any("4 steps inserted or deleted" in reason for reason in policy.reasons)


def test_the_strongest_trigger_wins_and_every_trigger_is_listed():
    operations = [
        op("update_ref", op_id="op-1"),
        op("add_requirement", {"requirement": "spare"}, op_id="op-2"),
        op("replace_text", {"old": "a", "new": "b"}, op_id="op-3"),
    ]
    policy = vs.suggest_policy(operations)
    assert policy.suggested == "new_issue" and len(policy.reasons) == 3


def test_no_operation_suggests_nothing_to_version():
    policy = vs.suggest_policy([])
    assert (policy.suggested, policy.mode) == ("none", "none") and policy.reasons
