"""Tests of redactech.agents.a4_locator."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.agents import a4_locator as a4
from redactech.models import Operation, SourceRef, SourceSpan, Target
from redactech.s1000d import index as ix
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED_KEY = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US"


def workspace_for(folder: Path, **overrides) -> wsmod.Workspace:
    folder = folder.resolve()
    values = {"id": "fixtures", "path": folder, "brex_dirs": [folder], "issue": "4.1"}
    return wsmod.Workspace([wsmod.Source(**{**values, **overrides})], folder)


@pytest.fixture(scope="module")
def idx() -> ix.CorpusIndex:
    return ix.build_index(workspace_for(FIXTURES))


def replace_part(old: str, new: str = "NEW-1", op_id: str = "op-0001") -> Operation:
    return Operation(
        id=op_id,
        kind="replace_part",
        target=Target(),
        params={"old": old, "new": new},
        rationale="test",
        source=[SourceSpan(doc="m.csv", quote=f"{old};{new}")],
    )


def other_op(kind: str, params: dict, target: Target) -> Operation:
    return Operation(
        id="op-0002",
        kind=kind,
        target=target,
        params=params,
        rationale="test",
        source=[SourceSpan(doc="form", quote="{}")],
    )


def short(ref: SourceRef) -> str:
    return ref.doc_key.removeprefix(f"DMC-RTPROTO-{CODE}-").split("_")[0]


def write_dm(folder: Path, body: str, name: str = "040A-A") -> None:
    xml = f"<dmodule><identAndStatusSection/><content>{body}</content></dmodule>"
    path = folder / f"DMC-SYNTH-AAA-D00-00-00-00AA-{name}_001-00_EN-US.XML"
    path.write_text(xml, encoding="utf-8")


# --- replace_part on the fixtures ---------------------------------------------


def test_lru1010_gives_three_writable_zones_and_two_skipped_update_traces(idx: ix.CorpusIndex):
    result = a4.locate(replace_part("LRU1010", "LRU2020"), idx)
    assert [(short(z.ref), z.certainty) for z in result.content_zones] == [
        ("040A-A", "probable"),  # free text
        ("0A3A-D", "certain"),  # comrep declaration
        ("941A-D", "certain"),  # IPD reference
    ]
    assert result.illustration_zones == []
    assert [z.id for z in result.zones] == ["zone-op-0001-1", "zone-op-0001-2", "zone-op-0001-3"]
    assert {(z.found_by, z.kind, z.operation_id) for z in result.zones} == {
        ("code", "content", "op-0001")
    }
    assert sorted(s.kind for s in result.skipped_readonly) == ["para", "partIdent"]
    assert all(s.ref.doc_key.startswith("UPF-") for s in result.skipped_readonly)
    assert all("read-only document (upf)" in s.reason for s in result.skipped_readonly)


def test_zones_point_at_the_occurrences(idx: ix.CorpusIndex):
    result = a4.locate(replace_part("LRU1010"), idx)
    by_file = {short(z.ref): z for z in result.zones}
    assert by_file["941A-D"].xpath.endswith("/partRef")
    assert "partSpec" in by_file["0A3A-D"].xpath and by_file["0A3A-D"].xpath.endswith("/partIdent")
    assert "LRU1010" in by_file["0A3A-D"].reason and "partSpec" in by_file["0A3A-D"].reason


def test_x2_zones_include_the_requirement_part_number(idx: ix.CorpusIndex):
    result = a4.locate(replace_part("X2"), idx)
    assert sorted(short(z.ref) for z in result.content_zones) == [
        "040A-A", "0A3A-D", "520A-A", "941A-D",
    ]
    spare = next(z for z in result.zones if short(z.ref) == "520A-A")
    assert spare.element_id == "spr-0001" and spare.certainty == "certain"
    assert result.skipped_readonly == []


def test_unknown_part_gives_no_zone(idx: ix.CorpusIndex):
    result = a4.locate(replace_part("NOPE-1"), idx)
    assert result.zones == [] and result.skipped_readonly == []


def test_read_only_source_gives_only_skipped_occurrences():
    index = ix.build_index(workspace_for(FIXTURES, writable=False))
    result = a4.locate(replace_part("LRU1010"), index)
    assert result.zones == [] and len(result.skipped_readonly) == 5


def test_replace_part_needs_the_old_value(idx: ix.CorpusIndex):
    op = replace_part("X")
    op.params.pop("old")
    with pytest.raises(a4.LocateError):
        a4.locate(op, idx)


# --- illustration zones -------------------------------------------------------


def test_figure_referenced_in_the_modified_step_gets_an_illustration_zone(tmp_path: Path):
    write_dm(
        tmp_path,
        '<levelledPara id="lp1"><para>See <internalRef internalRefId="fig-1" '
        'internalRefTargetType="irtt01"/> for PN-5.</para>'
        '<figure id="fig-1"><title>T</title><graphic infoEntityIdent="ICN-A"/></figure>'
        "</levelledPara>"
        '<levelledPara id="lp2"><para>Other.</para>'
        '<figure id="fig-2"><title>U</title><graphic infoEntityIdent="ICN-B"/></figure>'
        "</levelledPara>",
    )
    index = ix.build_index(workspace_for(tmp_path))
    result = a4.locate(replace_part("PN-5"), index)
    (content,) = result.content_zones
    (figure,) = result.illustration_zones
    assert content.certainty == "probable"
    assert (figure.kind, figure.certainty, figure.found_by) == ("illustration", "to_check", "code")
    assert figure.element_id == "fig-1" and figure.xpath.endswith("/levelledPara[1]/figure")
    assert figure.ref == content.ref and "fig-1" in figure.reason
    assert figure.operation_id == "op-0001" and figure.id != content.id


def test_figures_of_the_catalogue_are_flagged_for_an_ipd_item(tmp_path: Path):
    item = (
        '<catalogSeqNumber figureNumber="01" item="00{n}" indenture="1">'
        '<itemSeqNumber itemSeqNumberValue="00{n}">'
        '<partRef manufacturerCodeValue="M" partNumberValue="PN-6"/></itemSeqNumber>'
        "</catalogSeqNumber>"
    )
    write_dm(
        tmp_path,
        '<illustratedPartsCatalog><figure id="f1"><title>T</title>'
        '<graphic infoEntityIdent="ICN-X"/></figure>'
        + item.format(n=1)
        + item.format(n=2)
        + "</illustratedPartsCatalog>",
    )
    result = a4.locate(replace_part("PN-6"), ix.build_index(workspace_for(tmp_path)))
    assert [z.certainty for z in result.content_zones] == ["certain", "certain"]
    (figure,) = result.illustration_zones  # one flag for the figure, not one per item
    assert figure.element_id == "f1"


def test_no_figure_no_illustration_zone(tmp_path: Path):
    write_dm(tmp_path, "<para>PN-5 here</para>")
    result = a4.locate(replace_part("PN-5"), ix.build_index(workspace_for(tmp_path)))
    assert len(result.zones) == 1 and result.illustration_zones == []


# --- other operations ---------------------------------------------------------


def test_other_operations_get_a_zone_from_their_target(idx: ix.CorpusIndex):
    target = Target(ref=SourceRef(source_id="fixtures", doc_key=PROCED_KEY), element_id="stp-0002")
    result = a4.locate(other_op("insert_step", {"after_id": "stp-0002", "para": "x"}, target), idx)
    (zone,) = result.zones
    assert zone.ref.doc_key == PROCED_KEY and zone.element_id == "stp-0002"
    assert (zone.kind, zone.certainty, zone.operation_id) == ("content", "certain", "op-0002")
    assert result.skipped_readonly == []


def test_target_element_falls_back_to_the_step_parameters(idx: ix.CorpusIndex):
    target = Target(ref=SourceRef(source_id="fixtures", doc_key=PROCED_KEY))
    (zone,) = a4.locate(other_op("delete_step", {"step_id": "stp-0003"}, target), idx).zones
    assert zone.element_id == "stp-0003"
    (zone,) = a4.locate(other_op("move_step", {"step_id": "a", "after_id": "b"}, target), idx).zones
    assert zone.element_id == "a"
    explicit = Target(ref=target.ref, xpath="/dmodule/content", element_id=None)
    (zone,) = a4.locate(other_op("replace_text", {"old": "a", "new": "b"}, explicit), idx).zones
    assert zone.xpath == "/dmodule/content" and zone.element_id is None


def test_read_only_target_is_skipped(idx: ix.CorpusIndex):
    upf = next(d for d in idx.docs.values() if d.role == "upf")
    target = Target(ref=upf.ref, xpath="/dataUpdateFile")
    result = a4.locate(other_op("replace_text", {"old": "a", "new": "b"}, target), idx)
    assert result.zones == [] and len(result.skipped_readonly) == 1
    assert "upf" in result.skipped_readonly[0].reason


def test_target_errors(idx: ix.CorpusIndex):
    with pytest.raises(a4.LocateError):
        a4.locate(other_op("delete_step", {"step_id": "a"}, Target()), idx)
    ghost = Target(ref=SourceRef(source_id="fixtures", doc_key="ghost"))
    with pytest.raises(a4.LocateError):
        a4.locate(other_op("delete_step", {"step_id": "a"}, ghost), idx)


# --- real Bike data (skipped when data/ is absent) ----------------------------


@pytest.mark.data41
def test_real_bike_41_lru1010_has_two_writable_zones_and_two_skipped_traces(repo_root: Path):
    data = repo_root / "data" / "s1000d-4.1"
    source = wsmod.Source(
        id="bike41",
        path=(data / "bike").resolve(),
        brex_dirs=[(data / "brex").resolve()],
        issue="4.1",
        schemas_dir=(data / "schemas").resolve(),
    )
    index = ix.build_index(wsmod.Workspace([source], repo_root))
    result = a4.locate(replace_part("LRU1010", "LRU2020"), index)
    kinds = sorted(index_occurrence_kind(index, z) for z in result.content_zones)
    assert kinds == ["partRef", "partSpec"]
    assert all(z.certainty == "certain" for z in result.content_zones)
    assert len(result.skipped_readonly) == 2
    assert {s.ref.doc_key.split("-")[0] for s in result.skipped_readonly} == {"UPF"}
    assert sorted(s.kind for s in result.skipped_readonly) == ["para", "partIdent"]
    print(f"illustration zones flagged on Bike 4.1: {len(result.illustration_zones)}")


def index_occurrence_kind(index: ix.CorpusIndex, zone) -> str:
    for occ in ix.find_part(index, "LRU1010"):
        if occ.ref == zone.ref and occ.xpath == zone.xpath:
            return occ.kind
    raise AssertionError("zone without occurrence")
