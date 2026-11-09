"""Tests of redactech.agents.a5_preparer."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.agents import a4_locator as a4
from redactech.agents import a5_preparer as a5
from redactech.models import Operation, SourceRef, SourceSpan, Target, Zone
from redactech.s1000d import index as ix
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED_KEY = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US"


def workspace_for(folder: Path) -> wsmod.Workspace:
    folder = folder.resolve()
    source = wsmod.Source("fixtures", folder, [folder], "4.1")
    return wsmod.Workspace([source], folder)


@pytest.fixture(scope="module")
def idx() -> ix.CorpusIndex:
    return ix.build_index(workspace_for(FIXTURES))


def operation(kind: str, params: dict, target: Target | None = None, op_id: str = "op-0001"):
    return Operation(
        id=op_id,
        kind=kind,
        target=target or Target(),
        params=params,
        rationale="test",
        source=[SourceSpan(doc="m", quote="q")],
    )


def replace_part(old: str = "LRU1010", new: str = "LRU2020") -> Operation:
    return operation("replace_part", {"old": old, "new": new})


def proced_target(element_id: str | None = None) -> Target:
    ref = SourceRef(source_id="fixtures", doc_key=PROCED_KEY)
    return Target(ref=ref, element_id=element_id)


def write_dm(folder: Path, body: str) -> None:
    xml = f"<dmodule><identAndStatusSection/><content>{body}</content></dmodule>"
    path = folder / "DMC-SYNTH-AAA-D00-00-00-00AA-040A-A_001-00_EN-US.XML"
    path.write_text(xml, encoding="utf-8")


# --- basic proposals ----------------------------------------------------------


def test_lru1010_proposals_on_the_fixtures(idx: ix.CorpusIndex):
    op = replace_part()
    zones = a4.locate(op, idx).zones
    proposals = a5.prepare(op, zones, idx)
    assert [p.id for p in proposals] == ["prop-op-0001-1", "prop-op-0001-2", "prop-op-0001-3"]
    assert [p.zone_id for p in proposals] == [z.id for z in zones]
    assert [p.ref for p in proposals] == [z.ref for z in zones]
    for proposal in proposals:
        assert proposal.operation_id == "op-0001" and proposal.status == "proposed"
        assert (proposal.change_type, proposal.attempt, proposal.checks) == ("modify", 1, [])
        assert proposal.replaces is None and proposal.rejection_feedback == []
        assert "LRU1010" in proposal.before_xml and "LRU1010" not in proposal.after_xml
        # veracity: the only difference is the new value
        assert proposal.before_xml.replace("LRU1010", "LRU2020") == proposal.after_xml


def test_preparing_changes_nothing_on_disk_and_is_deterministic(idx: ix.CorpusIndex):
    before = {p.name: p.read_bytes() for p in FIXTURES.glob("*.XML")}
    op = replace_part()
    zones = a4.locate(op, idx).zones
    first = a5.prepare(op, zones, idx)
    assert first == a5.prepare(op, zones, idx)
    assert {p.name: p.read_bytes() for p in FIXTURES.glob("*.XML")} == before


def test_each_proposal_is_computed_on_its_own_copy(idx: ix.CorpusIndex):
    """Two zones of one document: the second proposal does not contain the first change."""
    op = replace_part("FAKE-PN-001", "FAKE-PN-002")
    zones = a4.locate(op, idx).zones
    proposals = a5.prepare(op, zones, idx)
    assert len(proposals) == 3
    for proposal in proposals:
        assert proposal.before_xml.count("FAKE-PN-001") == 1
        assert proposal.after_xml.count("FAKE-PN-002") == 1


def test_zones_that_fail_are_reported_not_fatal(idx: ix.CorpusIndex):
    op = replace_part()
    good = a4.locate(op, idx).zones[0]
    bad = good.model_copy(update={"id": "zone-bad", "xpath": "//nothing", "element_id": None})
    report = a5.prepare_report(op, [bad, good], idx)
    assert [p.id for p in report.proposals] == ["prop-op-0001-2"]  # numbering follows the zones
    assert len(report.errors) == 1 and report.errors[0].startswith("zone-bad")


def test_other_operations(idx: ix.CorpusIndex):
    insert = operation(
        "insert_step", {"after_id": "stp-0002", "para": "Check."}, proced_target("stp-0002"), "op-2"
    )
    (proposal,) = a5.prepare(insert, a4.locate(insert, idx).zones, idx)
    assert proposal.change_type == "add" and proposal.before_xml == ""
    assert 'id="stp-0006"' in proposal.after_xml and proposal.id == "prop-op-2-1"
    delete = operation("delete_step", {"step_id": "stp-0003"}, proced_target(), "op-3")
    (proposal,) = a5.prepare(delete, a4.locate(delete, idx).zones, idx)
    assert proposal.change_type == "delete" and proposal.before_xml == proposal.after_xml


def test_unsupported_operation_is_an_error_not_a_proposal(idx: ix.CorpusIndex):
    op = operation("translate_dm", {}, proced_target("stp-0001"), "op-9")
    zone = Zone(
        id="z", ref=proced_target().ref, xpath="", element_id="stp-0001", certainty="certain",
        found_by="code", reason="r", operation_id="op-9",
    )
    report = a5.prepare_report(op, [zone], idx)
    assert report.proposals == [] and "not implemented" in report.errors[0]


# --- illustration zones -------------------------------------------------------


def test_illustration_zone_gives_a_flag_only_proposal(tmp_path: Path):
    write_dm(
        tmp_path,
        '<levelledPara id="lp1"><para>See <internalRef internalRefId="fig-1" '
        'internalRefTargetType="irtt01"/> for PN-5.</para>'
        '<figure id="fig-1"><title>T</title><graphic infoEntityIdent="ICN-A"/></figure>'
        "</levelledPara>",
    )
    index = ix.build_index(workspace_for(tmp_path))
    op = replace_part("PN-5", "PN-6")
    zones = a4.locate(op, index).zones
    content, flag = a5.prepare(op, zones, index)
    assert "PN-6" in content.after_xml and content.checks == []
    assert flag.id == "prop-op-0001-2" and flag.zone_id == zones[1].id
    assert flag.before_xml == flag.after_xml and flag.before_xml.startswith("<figure")
    assert (flag.status, flag.change_type) == ("proposed", "modify")
    (check,) = flag.checks
    assert (check.name, check.ok, check.severity) == ("illustration", False, "warning")
    assert check.details.startswith("to check") and check.ref == zones[1].ref


# --- alternatives after a rejection -------------------------------------------


def twice(tmp_path: Path) -> tuple[ix.CorpusIndex, Operation, list[Zone]]:
    write_dm(tmp_path, "<para>PN-1 and PN-1</para>")
    index = ix.build_index(workspace_for(tmp_path))
    op = replace_part("PN-1", "PN-2")
    return index, op, a4.locate(op, index).zones


def test_free_text_with_two_mentions_offers_first_then_last(tmp_path: Path):
    index, op, zones = twice(tmp_path)
    (first,) = a5.prepare(op, zones, index)
    assert first.after_xml == "<para>PN-2 and PN-2</para>"
    (alt1,) = a5.prepare(op, zones, index, a5.Rejection(first, "too much"))
    assert alt1.after_xml == "<para>PN-2 and PN-1</para>"
    assert (alt1.attempt, alt1.replaces, alt1.id) == (2, first.id, f"{first.id}-a2")
    assert alt1.rejection_feedback == ["too much"] and alt1.status == "proposed"
    assert alt1.zone_id == first.zone_id
    assert alt1.operation_id == f"op-0001-a2-{first.zone_id}"  # a derived operation
    report = a5.prepare_report(op, zones, index, a5.Rejection(first, "too much"))
    (derived,) = report.operations
    assert derived.id == alt1.operation_id and derived.params["occurrence"] == 1
    assert derived.params["old"] == "PN-1" and op.params.get("occurrence") is None
    (alt2,) = a5.prepare(op, zones, index, a5.Rejection(alt1, "still not"))
    assert alt2.after_xml == "<para>PN-1 and PN-2</para>"
    assert (alt2.attempt, alt2.replaces) == (3, alt1.id)
    assert alt2.rejection_feedback == ["too much", "still not"]
    assert a5.prepare(op, zones, index, a5.Rejection(alt2)) == []  # nothing left: manual edit


def test_rejection_without_feedback_keeps_the_history(tmp_path: Path):
    index, op, zones = twice(tmp_path)
    (first,) = a5.prepare(op, zones, index)
    (alt,) = a5.prepare(op, zones, index, a5.Rejection(first))
    assert alt.rejection_feedback == []


def test_max_alternatives_is_respected(tmp_path: Path):
    index, op, zones = twice(tmp_path)
    (first,) = a5.prepare(op, zones, index)
    (alt1,) = a5.prepare(op, zones, index, a5.Rejection(first), max_alternatives=1)
    assert a5.prepare(op, zones, index, a5.Rejection(alt1), max_alternatives=1) == []
    assert a5.prepare(op, zones, index, a5.Rejection(first), max_alternatives=0) == []


def test_structured_zone_has_no_alternative(idx: ix.CorpusIndex):
    op = replace_part()
    zones = a4.locate(op, idx).zones
    proposals = a5.prepare(op, zones, idx)
    ipd = next(p for p in proposals if "partRef" in p.before_xml)
    assert a5.prepare(op, zones, idx, a5.Rejection(ipd, "no")) == []


def test_single_mention_has_no_alternative(tmp_path: Path):
    write_dm(tmp_path, "<para>only PN-1 here</para>")
    index = ix.build_index(workspace_for(tmp_path))
    op = replace_part("PN-1", "PN-2")
    zones = a4.locate(op, index).zones
    (first,) = a5.prepare(op, zones, index)
    assert a5.prepare(op, zones, index, a5.Rejection(first)) == []


def test_replace_with_an_explicit_occurrence_has_no_alternative(tmp_path: Path):
    index, op, zones = twice(tmp_path)
    op.params["occurrence"] = 1
    (first,) = a5.prepare(op, zones, index)
    assert first.after_xml == "<para>PN-2 and PN-1</para>"
    assert a5.prepare(op, zones, index, a5.Rejection(first)) == []


def test_unknown_zone_or_illustration_zone_gives_no_alternative(idx: ix.CorpusIndex):
    op = replace_part()
    zones = a4.locate(op, idx).zones
    first = a5.prepare(op, zones, idx)[0]
    stray = first.model_copy(update={"zone_id": "elsewhere"})
    assert a5.prepare(op, zones, idx, a5.Rejection(stray)) == []
    flag_zone = zones[0].model_copy(update={"kind": "illustration"})
    assert a5.prepare(op, [flag_zone], idx, a5.Rejection(first)) == []


def test_insert_step_alternatives_are_the_neighbouring_positions(idx: ix.CorpusIndex):
    op = operation(
        "insert_step", {"after_id": "stp-0002", "para": "Check."}, proced_target("stp-0002"), "op-2"
    )
    zones = a4.locate(op, idx).zones
    (first,) = a5.prepare(op, zones, idx)
    (alt1,) = a5.prepare(op, zones, idx, a5.Rejection(first))
    (alt2,) = a5.prepare(op, zones, idx, a5.Rejection(alt1))
    assert (alt1.attempt, alt2.attempt) == (2, 3) and alt1.replaces == first.id
    assert a5.prepare(op, zones, idx, a5.Rejection(alt2)) == []
    assert alt1.change_type == alt2.change_type == "add"


def test_insert_step_before_the_first_step_has_one_alternative(idx: ix.CorpusIndex):
    params = {"before_id": "stp-0001", "para": "First."}
    op = operation("insert_step", params, proced_target("stp-0001"), "op-2")
    zones = a4.locate(op, idx).zones
    (first,) = a5.prepare(op, zones, idx)
    (alt,) = a5.prepare(op, zones, idx, a5.Rejection(first))
    assert a5.prepare(op, zones, idx, a5.Rejection(alt)) == []


def test_move_step_alternatives_change_the_resulting_order(idx: ix.CorpusIndex):
    op = operation(
        "move_step", {"step_id": "stp-0005", "after_id": "stp-0001"}, proced_target(), "op-4"
    )
    zones = a4.locate(op, idx).zones
    (first,) = a5.prepare(op, zones, idx)
    (alt1,) = a5.prepare(op, zones, idx, a5.Rejection(first))
    (alt2,) = a5.prepare(op, zones, idx, a5.Rejection(alt1))
    assert len({first.after_xml, alt1.after_xml, alt2.after_xml}) == 3
    assert a5.prepare(op, zones, idx, a5.Rejection(alt2)) == []


def test_delete_step_has_no_alternative(idx: ix.CorpusIndex):
    op = operation("delete_step", {"step_id": "stp-0003"}, proced_target(), "op-3")
    zones = a4.locate(op, idx).zones
    (first,) = a5.prepare(op, zones, idx)
    assert a5.prepare(op, zones, idx, a5.Rejection(first)) == []


# --- real Bike data (skipped when data/ is absent) ----------------------------


@pytest.mark.data41
def test_real_bike_41_lru1010_proposals(repo_root: Path):
    data = repo_root / "data" / "s1000d-4.1"
    source = wsmod.Source(
        "bike41", (data / "bike").resolve(), [(data / "brex").resolve()], "4.1",
        schemas_dir=(data / "schemas").resolve(),
    )
    index = ix.build_index(wsmod.Workspace([source], repo_root))
    op = replace_part()
    located = a4.locate(op, index)
    report = a5.prepare_report(op, located.zones, index)
    assert report.errors == []
    content = [p for p in report.proposals if p.checks == []]
    assert len(content) == 2 and len(located.skipped_readonly) == 2
    for proposal in content:
        assert proposal.before_xml.replace("LRU1010", "LRU2020") == proposal.after_xml
