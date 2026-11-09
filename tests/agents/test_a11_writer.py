"""Tests of redactech.agents.a11_writer (decided proposals -> new data modules)."""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

import pytest

from redactech.agents import a4_locator as a4
from redactech.agents import a5_preparer as a5
from redactech.agents.a11_writer import WriteRefused, write
from redactech.config import TraceConfig
from redactech.models import (
    Operation,
    Proposal,
    SourceRef,
    SourceSpan,
    Target,
    VersionPolicy,
    Zone,
)
from redactech.s1000d import index as ix
from redactech.s1000d import io as xio
from redactech.s1000d import validate
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
COMREP = f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
UPF = f"UPF-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
ALL = (PROCED, MARKED, IPD, COMREP, UPF, PROJECT, DEFAULT)
TODAY = datetime.date(2025, 3, 7)
IN_WORK = VersionPolicy(mode="in_work", suggested="in_work")
NO_VERSION = VersionPolicy(mode="none", suggested="none")
NEW_ISSUE = VersionPolicy(mode="new_issue", suggested="new_issue")

MINI_PROCED_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="anyContent" mixed="true">
    <xs:sequence><xs:any processContents="skip" minOccurs="0" maxOccurs="unbounded"/></xs:sequence>
    <xs:anyAttribute processContents="skip"/>
  </xs:complexType>
  <xs:element name="dmodule">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="identAndStatusSection" type="anyContent"/>
        <xs:element name="content" type="anyContent"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


class Plan:
    """A source folder, its index, and the operations / zones / proposals prepared on it."""

    def __init__(self, tmp_path: Path, names: tuple[str, ...] = ALL):
        self.src = tmp_path / "src"
        self.src.mkdir()
        for name in names:
            shutil.copy(FIXTURES / name, self.src / name)
        folder = self.src.resolve()
        source = wsmod.Source("fixtures", folder, [folder], "4.1")
        self.workspace = wsmod.Workspace([source], folder)
        self.index = ix.build_index(self.workspace)
        self.run_dir = tmp_path / "run"
        self.operations: list[Operation] = []
        self.zones: list[Zone] = []
        self.proposals: list[Proposal] = []

    def add(self, op: Operation) -> list[Proposal]:
        zones = a4.locate(op, self.index).zones
        proposals = a5.prepare(op, zones, self.index)
        self.operations.append(op)
        self.zones += zones
        self.proposals += proposals
        return proposals

    def snapshot(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in self.src.iterdir()}

    def write(self, policy: VersionPolicy = IN_WORK, **kwargs):
        return write(
            self.run_dir,
            self.index,
            self.proposals,
            policy,
            operations=self.operations,
            zones=self.zones,
            today=TODAY,
            **kwargs,
        )


def operation(kind: str, params: dict, target: Target | None = None, number: int = 1):
    return Operation(
        id=f"op-{number:04d}",
        kind=kind,
        target=target or Target(),
        params=params,
        rationale=f"reason {number}",
        source=[SourceSpan(doc="m", quote="q")],
    )


def decide(proposals: list[Proposal], status: str, only: str | None = None) -> list[Proposal]:
    """Copies of the proposals with a status (those whose document name contains ``only``)."""
    return [
        p.model_copy(update={"status": status}) if only is None or only in p.ref.doc_key else p
        for p in proposals
    ]


def target(name: str, element_id: str | None = None) -> Target:
    ref = SourceRef(source_id="fixtures", doc_key=name.removesuffix(".XML"))
    return Target(ref=ref, element_id=element_id)


def replace_x2() -> Operation:
    return operation("replace_part", {"old": "X2", "new": "X3"})


def out_doc(path: Path) -> xio.XmlDoc:
    return xio.load(path)


def find(doc: xio.XmlDoc, expr: str):
    return xio.xpath(doc.root, expr)


# --- what gets written --------------------------------------------------------


def test_accepted_is_written_rejected_and_pending_are_not(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "rejected")
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    plan.proposals = [
        p.model_copy(update={"status": "pending_client"}) if "0A3A" in p.ref.doc_key else p
        for p in plan.proposals
    ]
    before = plan.snapshot()
    result = plan.write()
    assert [p.name for p in result.written] == [PROCED.replace("001-00", "001-01")]
    assert sorted(p.name for p in (plan.run_dir / "out").iterdir()) == [result.written[0].name]
    assert plan.snapshot() == before  # the sources are byte-identical
    doc = out_doc(result.written[0])
    (number,) = find(doc, "//spareDescr//partNumber")
    assert number.text == "X3"
    assert (number.get("changeMark"), number.get("changeType")) == ("1", "modify")
    assert number.get("reasonForUpdateRefIds") == "rfu-0001"
    (reason,) = find(doc, "//reasonForUpdate")
    assert reason.get("id") == "rfu-0001" and reason.find("simplePara").text == "reason 1"
    info = find(doc, "//dmIdent/issueInfo")[0]
    assert (info.get("issueNumber"), info.get("inWork")) == ("001", "01")
    (entry,) = result.log
    assert (entry["old_name"], entry["policy"]) == (PROCED, "in_work")
    assert entry["new_name"] == result.written[0].name
    assert [m["change_type"] for m in entry["marks"]] == ["modify"]


def test_edited_proposals_use_the_edited_xml(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    edited = '<partRef manufacturerCodeValue="FAKE1" partNumberValue="X9"/>'
    plan.proposals = [
        p.model_copy(update={"status": "edited", "edited_xml": edited})
        if "941A" in p.ref.doc_key
        else p.model_copy(update={"status": "rejected"})
        for p in plan.proposals
    ]
    (path,) = plan.write().written
    (ref,) = find(out_doc(path), "//partRef[@partNumberValue='X9']")
    assert ref.get("changeType") == "modify" and ref.get("changeMark") == "1"
    assert "X3" not in path.read_text(encoding="utf-8")
    bad = [p.model_copy(update={"edited_xml": "<partRef"}) for p in plan.proposals]
    plan.proposals = bad
    with pytest.raises(WriteRefused):
        plan.write()


def test_a_proposal_still_proposed_blocks_the_whole_write(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    with pytest.raises(WriteRefused) as error:
        plan.write()
    assert "undecided" in str(error.value)
    assert not (plan.run_dir / "out").exists()  # nothing was written
    leftovers = {p.id for p in plan.proposals if p.status == "proposed"}
    result = plan.write(excluded=leftovers)  # explicit exclusion lifts the block
    assert len(result.written) == 1


def test_decisions_must_be_complete(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted")
    with pytest.raises(WriteRefused):
        plan.write(decided=False)
    assert not (plan.run_dir / "out").exists()


def test_read_only_documents_are_never_written(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    plan.proposals = decide(plan.proposals, "rejected", only="941A")
    plan.proposals = decide(plan.proposals, "rejected", only="0A3A")
    upf = next(d for d in plan.index.docs.values() if d.role == "upf")
    zone = Zone(
        id="zone-upf",
        ref=upf.ref,
        xpath="/dataUpdateFile",
        element_id=None,
        certainty="certain",
        found_by="code",
        reason="r",
        operation_id="op-0001",
    )
    forced = Proposal(
        id="prop-upf",
        operation_id="op-0001",
        zone_id="zone-upf",
        ref=upf.ref,
        before_xml="<a/>",
        after_xml="<b/>",
        change_type="modify",
        status="accepted",
    )
    plan.zones.append(zone)
    plan.proposals.append(forced)
    result = plan.write()
    assert [p.name for p in result.written] == [PROCED.replace("001-00", "001-01")]
    assert any("read-only document (upf)" in s["reason"] for s in result.skipped)
    assert not any(UPF.split("_")[0] in p.name for p in (plan.run_dir / "out").iterdir())


def test_illustration_flags_are_not_written(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    flag_zone = plan.zones[0].model_copy(update={"id": "zone-flag", "kind": "illustration"})
    flag = plan.proposals[0].model_copy(
        update={"id": "prop-flag", "zone_id": "zone-flag", "status": "accepted"}
    )
    plan.zones.append(flag_zone)
    plan.proposals = [*decide(plan.proposals, "rejected"), flag]
    result = plan.write()
    assert result.written == [] and result.skipped[0]["reason"].startswith("flag only")


def test_unknown_zone_or_failing_operation_refuses_everything(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted")
    plan.zones = []
    with pytest.raises(WriteRefused):
        plan.write()
    plan.zones = [z.model_copy(update={"xpath": "//nothing", "element_id": None})
                  for z in a4.locate(plan.operations[0], plan.index).zones]
    with pytest.raises(WriteRefused):
        plan.write()
    assert not (plan.run_dir / "out").exists()


# --- marks, deletion, policies ------------------------------------------------


def test_delete_is_only_a_mark(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(operation("delete_step", {"step_id": "stp-0003"}, target(PROCED)))
    plan.proposals = decide(plan.proposals, "accepted")
    result = plan.write(NO_VERSION)
    (path,) = result.written
    assert path.name == PROCED  # policy none keeps the name
    doc = out_doc(path)
    steps = find(doc, "//proceduralStep")
    assert len(steps) == 5  # the step is still there
    marked = [s for s in steps if s.get("changeType") == "delete"]
    assert [s.get("id") for s in marked] == ["stp-0003"] and marked[0].get("changeMark") == "1"
    assert find(doc, "//reasonForUpdate")[0].find("simplePara").text == "reason 1"
    info = find(doc, "//dmIdent/issueInfo")[0]
    assert (info.get("issueNumber"), info.get("inWork")) == ("001", "00")


def test_marks_can_be_switched_off_with_policy_none(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    plan.proposals = decide(plan.proposals, "rejected", only="941A")
    plan.proposals = decide(plan.proposals, "rejected", only="0A3A")
    result = plan.write(NO_VERSION, trace_config=TraceConfig(marks_when_none=False))
    text = result.written[0].read_text(encoding="utf-8")
    assert "changeMark" not in text and "reasonForUpdate" not in text and "X3" in text
    assert result.log[0]["marks"] == []


def test_new_issue_consolidates_then_marks_this_cycle(tmp_path: Path):
    plan = Plan(tmp_path)
    step = target(MARKED, "stp-0001")
    plan.add(operation("insert_step", {"after_id": "stp-0001", "para": "Check."}, step))
    plan.proposals = decide(plan.proposals, "accepted")
    (path,) = plan.write(NEW_ISSUE).written
    assert path.name == MARKED.replace("007-00", "008-00")
    doc = out_doc(path)
    assert [s.get("id") for s in find(doc, "//proceduralStep")] == [
        "stp-0001",
        "stp-0004",  # the id of the removed step is free again after consolidation
        "stp-0002",
        "stp-0003",
    ]
    marked = [e for e in doc.root.iter() if isinstance(e.tag, str) and e.get("changeMark")]
    assert [(e.get("id"), e.get("changeType")) for e in marked] == [("stp-0004", "add")]
    assert [r.get("id") for r in find(doc, "//reasonForUpdate")] == ["rfu-0001"]
    info = find(doc, "//dmIdent/issueInfo")[0]
    assert (info.get("issueNumber"), info.get("inWork")) == ("008", "00")


def test_per_document_policy_overrides_the_default(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    plan.proposals = decide(plan.proposals, "rejected", only="941A")
    plan.proposals = decide(plan.proposals, "rejected", only="0A3A")
    policy = VersionPolicy(
        mode="none", suggested="none", per_doc={stem_of(PROCED): "in_work"}
    )
    (path,) = plan.write(policy).written
    assert path.name == PROCED.replace("001-00", "001-01")


def stem_of(name: str) -> str:
    return name.removesuffix(".XML")


def test_several_operations_on_one_document(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.add(operation("replace_part", {"old": "FAKE-PN-001", "new": "FAKE-PN-002"}, number=2))
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    plan.proposals = decide(plan.proposals, "rejected", only="941A")
    plan.proposals = decide(plan.proposals, "rejected", only="0A3A")
    (path,) = plan.write().written
    text = path.read_text(encoding="utf-8")
    assert "rt-target" not in text  # the temporary handles are gone
    doc = out_doc(path)
    numbers = [n.text for n in find(doc, "//partNumber")]
    assert sorted(numbers) == ["FAKE-PN-002", "FAKE-PN-002", "X3"]
    assert [r.find("simplePara").text for r in find(doc, "//reasonForUpdate")] == [
        "reason 1",
        "reason 2",
    ]
    assert len([e for e in doc.root.iter() if isinstance(e.tag, str) and e.get("changeMark")]) == 3


def test_written_module_is_valid_against_a_schema(tmp_path: Path):
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "proced.xsd").write_text(MINI_PROCED_XSD, encoding="utf-8")
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted", only="520A")
    plan.proposals = decide(plan.proposals, "rejected", only="941A")
    plan.proposals = decide(plan.proposals, "rejected", only="0A3A")
    (path,) = plan.write().written
    results = validate.check_xsd(out_doc(path), schemas)
    assert [r.ok for r in results] == [True]
    assert [r.ok for r in validate.check_ids(out_doc(path))] == [True]


def test_rerunning_the_write_overwrites_only_the_output(tmp_path: Path):
    plan = Plan(tmp_path)
    plan.add(replace_x2())
    plan.proposals = decide(plan.proposals, "accepted")
    first = plan.write()
    second = plan.write()
    assert [p.name for p in first.written] == [p.name for p in second.written]
    assert sorted(p.name for p in (plan.run_dir / "out").iterdir()) == sorted(
        p.name for p in second.written
    )


# --- new issue: positions are resolved before the consolidation -----------------------------


def deleted_step_first(plan: Plan) -> xio.XmlDoc:
    """520B with its deleted step moved to the front and a second paragraph mentioning 'step'."""
    path = plan.src / MARKED
    doc = xio.load(path)
    steps = {s.get("id"): s for s in xio.xpath(doc.root, "//proceduralStep")}
    steps["stp-0001"].addprevious(steps["stp-0004"])
    steps["stp-0002"].find("para").text = "Another step."
    xio.save(doc, path)
    plan.index = ix.build_index(plan.workspace)
    return xio.load(path)


def manual_proposal(plan: Plan, doc: xio.XmlDoc, step_id: str, number: int) -> None:
    """A replace_text of 'step' by 'STEP' in the paragraph of a step, zone xpath positional."""
    para = xio.xpath(doc.root, f"//proceduralStep[@id='{step_id}']/para")[0]
    key = f"fixtures:{MARKED.removesuffix('.XML')}"
    ref = plan.index.docs[key].ref
    zone = Zone(
        id=f"zone-{number}",
        ref=ref,
        xpath=para.getroottree().getpath(para),
        element_id=None,
        certainty="certain",
        found_by="code",
        reason="r",
        operation_id=f"op-{number:04d}",
    )
    op = operation("replace_text", {"old": "step", "new": "STEP"}, number=number)
    proposal = Proposal(
        id=f"prop-{number}",
        operation_id=op.id,
        zone_id=zone.id,
        ref=ref,
        before_xml="<para/>",
        after_xml="<para/>",
        change_type="modify",
        status="accepted",
    )
    plan.operations.append(op)
    plan.zones.append(zone)
    plan.proposals.append(proposal)


def test_new_issue_changes_the_decided_element_not_its_shifted_neighbour(tmp_path: Path):
    plan = Plan(tmp_path, (MARKED, PROJECT, DEFAULT))
    doc = deleted_step_first(plan)
    manual_proposal(plan, doc, "stp-0001", 1)  # positional xpath: proceduralStep[2]
    (path,) = plan.write(NEW_ISSUE).written
    paras = {s.get("id"): s.find("para").text for s in find(out_doc(path), "//proceduralStep")}
    assert paras["stp-0001"] == "Unchanged STEP."
    assert paras["stp-0002"] == "Another step."  # the shifted neighbour was not touched
    assert "stp-0004" not in paras  # consolidated


def test_new_issue_refuses_a_target_that_the_consolidation_removes(tmp_path: Path):
    plan = Plan(tmp_path, (MARKED, PROJECT, DEFAULT))
    doc = deleted_step_first(plan)
    manual_proposal(plan, doc, "stp-0004", 1)  # inside the step marked as deleted
    with pytest.raises(WriteRefused) as error:
        plan.write(NEW_ISSUE)
    assert "marked for deletion" in str(error.value) and "prop-1" in str(error.value)
    assert not (plan.run_dir / "out").exists()


def test_two_operations_on_one_paragraph_share_the_handle(tmp_path: Path):
    plan = Plan(tmp_path)
    doc = xio.load(plan.src / PROCED)
    para = xio.xpath(doc.root, "//proceduralStep[@id='stp-0003']/para")[0]
    where = Target(
        ref=plan.index.docs[f"fixtures:{PROCED.removesuffix('.XML')}"].ref,
        xpath=para.getroottree().getpath(para),
    )
    plan.add(operation("replace_text", {"old": "fasteners", "new": "bolts"}, where, 1))
    plan.add(operation("replace_text", {"old": "hand", "new": "wrench"}, where, 2))
    plan.proposals = decide(plan.proposals, "accepted")
    (path,) = plan.write().written
    out = out_doc(path)
    (changed,) = find(out, "//proceduralStep[@id='stp-0003']/para")
    assert changed.text == "Tighten the bolts by wrench."
    assert changed.get("reasonForUpdateRefIds") == "rfu-0001 rfu-0002"
    assert "rt-target" not in path.read_text(encoding="utf-8")


# --- real Bike data (skipped when data/ is absent) ----------------------------


@pytest.mark.data41
def test_real_bike_41_lru1010_is_written_and_sources_untouched(repo_root: Path, tmp_path: Path):
    data = repo_root / "data" / "s1000d-4.1"
    sources = {p.name: p.read_bytes() for p in (data / "bike").iterdir() if p.is_file()}
    source = wsmod.Source(
        "bike41",
        (data / "bike").resolve(),
        [(data / "brex").resolve()],
        "4.1",
        schemas_dir=(data / "schemas").resolve(),
    )
    index = ix.build_index(wsmod.Workspace([source], repo_root))
    op = operation("replace_part", {"old": "LRU1010", "new": "LRU2020"})
    zones = a4.locate(op, index).zones
    proposals = [
        p.model_copy(update={"status": "accepted"})
        for p in a5.prepare(op, zones, index)
        if p.checks == []
    ]
    result = write(
        tmp_path / "run", index, proposals, IN_WORK, operations=[op], zones=zones, today=TODAY
    )
    assert len(result.written) == 2
    for path in result.written:
        text = path.read_text(encoding="utf-8")
        assert "LRU2020" in text and "LRU1010" not in text and "changeMark" in text
        assert not path.name.startswith("UPF")
    assert {p.name: p.read_bytes() for p in (data / "bike").iterdir() if p.is_file()} == sources
