"""Tests of redactech.s1000d.index."""

from __future__ import annotations

import shutil
import types
from pathlib import Path

import pytest

from redactech.s1000d import index as ix
from redactech.s1000d import io as xio
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
PROJECT_KEY = f"RTPROTO-{CODE}-022A-D"
DEFAULT_KEY = f"RTDEFLT-{CODE}-022A-D"


def stem(name: str) -> str:
    return name.removesuffix(".XML")


def workspace_for(folder: Path, source_id: str = "fixtures", **overrides) -> wsmod.Workspace:
    folder = folder.resolve()
    values = {"id": source_id, "path": folder, "brex_dirs": [folder], "issue": "4.1"}
    return wsmod.Workspace([wsmod.Source(**{**values, **overrides})], folder)


def short(occ: ix.Occurrence) -> tuple[str, str, bool]:
    """(file, kind, writable) with the common name parts removed."""
    key = occ.ref.doc_key
    prefix = "UPF:" if key.startswith("UPF-") else ""
    for head in (f"DMC-RTPROTO-{CODE}-", f"UPF-RTPROTO-{CODE}-"):
        key = key.removeprefix(head)
    return prefix + key.split("_")[0], occ.kind, occ.writable


@pytest.fixture(scope="module")
def idx() -> ix.CorpusIndex:
    return ix.build_index(workspace_for(FIXTURES))


def write_dm(folder: Path, body: str, name: str = "040A-A") -> Path:
    path = folder / f"DMC-SYNTH-AAA-D00-00-00-00AA-{name}_001-00_EN-US.XML"
    xml = f"<dmodule><identAndStatusSection/><content>{body}</content></dmodule>"
    path.write_text(xml, encoding="utf-8")
    return path


# --- documents, BREX, chains --------------------------------------------------


def test_documents_and_counts(idx: ix.CorpusIndex):
    assert idx.counts() == {"fixtures": {"dm": 9, "brex": 2, "upf": 1}}
    assert f"fixtures:{stem(PROCED)}" in idx.docs
    assert idx.unreadable == {} and idx.warnings == []


def test_brex_index_per_source(idx: ix.CorpusIndex):
    assert set(idx.brex_index) == {"fixtures"}
    assert set(idx.brex_index["fixtures"]) == {PROJECT_KEY, DEFAULT_KEY}


def test_brex_chains_are_stored_in_the_documents(idx: ix.CorpusIndex):
    def chain(name: str) -> list[str]:
        return [r.doc_key for r in idx.docs[f"fixtures:{stem(name)}"].brex_chain]

    assert chain(PROCED) == [stem(PROJECT), stem(DEFAULT)]
    assert chain(PROJECT) == [stem(DEFAULT)]
    assert chain(DEFAULT) == [stem(DEFAULT)]
    assert all(r.source_id == "fixtures" for r in idx.docs[f"fixtures:{stem(PROCED)}"].brex_chain)


def test_chains_resolve_inside_each_source(tmp_path: Path):
    """Two sources with the same BREX code but different issues keep their own BREX."""
    ws = wsmod.Workspace(root=tmp_path)
    for source_id, issue in (("a", "008-00"), ("b", "009-00")):
        folder = tmp_path / source_id
        folder.mkdir()
        shutil.copy(FIXTURES / PROCED, folder / PROCED)
        shutil.copy(FIXTURES / PROJECT, folder / PROJECT.replace("001-00", issue))
        shutil.copy(FIXTURES / DEFAULT, folder / DEFAULT.replace("001-00", issue))
        ws.sources.append(wsmod.Source(source_id, folder.resolve(), [folder.resolve()], "4.1"))
    index = ix.build_index(ws)
    for source_id, issue in (("a", "008-00"), ("b", "009-00")):
        chain = index.docs[f"{source_id}:{stem(PROCED)}"].brex_chain
        assert [r.doc_key.split("_")[1] for r in chain] == [issue, issue]
        assert index.brex_index[source_id][PROJECT_KEY].name == PROJECT.replace("001-00", issue)


def test_unknown_brex_gives_a_warning_and_an_empty_chain(tmp_path: Path):
    shutil.copy(FIXTURES / PROCED, tmp_path / PROCED)
    index = ix.build_index(workspace_for(tmp_path))
    assert index.docs[f"fixtures:{stem(PROCED)}"].brex_chain == []
    assert len(index.warnings) == 1 and "not found" in index.warnings[0].details


# --- part numbers -------------------------------------------------------------


def test_find_part_lru1010_in_dms_and_update_files(idx: ix.CorpusIndex):
    found = ix.find_part(idx, "LRU1010")
    assert sorted(short(o) for o in found) == [
        ("040A-A", "para", True),  # free text mention
        ("0A3A-D", "partSpec", True),  # comrep declaration
        ("941A-D", "partRef", True),  # IPD reference
        ("UPF:0A3A-D", "para", False),  # update file: reason for update text
        ("UPF:0A3A-D", "partIdent", False),  # update file: deleted object
    ]


def test_find_part_details(idx: ix.CorpusIndex):
    by_kind = {o.kind: o for o in ix.find_part(idx, "LRU1010") if o.writable}
    ipd = by_kind["partRef"]
    assert ipd.context is not None and "catalogSeqNumber" in ipd.context
    assert ipd.xpath.endswith("/partRef") and ipd.value == "LRU1010"
    assert ipd.element_id is None
    assert "partSpec" in by_kind["partSpec"].xpath
    assert by_kind["para"].xpath.endswith("/para[1]") or "/para" in by_kind["para"].xpath


def test_find_part_x2(idx: ix.CorpusIndex):
    found = ix.find_part(idx, "X2")
    assert sorted(short(o) for o in found) == [
        ("040A-A", "para", True),
        ("0A3A-D", "partSpec", True),
        ("520A-A", "partNumber", True),
        ("941A-D", "partRef", True),
    ]
    spare = next(o for o in found if o.kind == "partNumber")
    assert "spareDescr" in spare.xpath and spare.element_id == "spr-0001"


def test_find_part_fake_pn(idx: ix.CorpusIndex):
    found = ix.find_part(idx, "FAKE-PN-001")
    assert sorted(short(o) for o in found) == [
        ("520A-A", "partNumber", True),
        ("520A-A", "partNumber", True),
        ("941A-D", "partRef", True),
    ]


def test_find_part_unknown_and_empty(idx: ix.CorpusIndex):
    assert ix.find_part(idx, "NOPE-1") == []
    assert ix.find_part(idx, "") == []


def test_read_only_source_flags_every_occurrence(tmp_path: Path):
    name = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
    shutil.copy(FIXTURES / name, tmp_path / name)
    index = ix.build_index(workspace_for(tmp_path, writable=False))
    found = ix.find_part(index, "LRU1010")
    assert len(found) == 1 and found[0].writable is False


@pytest.mark.parametrize(
    "text,token,expected",
    [
        ("see LRU1010.", "LRU1010", True),
        ("(LRU1010)", "LRU1010", True),
        ("a LRU1010, b", "LRU1010", True),
        ("LRU1010", "LRU1010", True),
        ("LRU10100", "LRU1010", False),
        ("XLRU1010", "LRU1010", False),
        ("LRU1010-A", "LRU1010", False),
        ("A-LRU1010", "LRU1010", False),
        ("LRU10100 and LRU1010", "LRU1010", True),
        ("nothing", "LRU1010", False),
        ("anything", "", False),
    ],
)
def test_contains_token(text: str, token: str, expected: bool):
    assert ix.contains_token(text, token) is expected


def test_free_text_is_counted_once_per_paragraph_without_nesting(tmp_path: Path):
    write_dm(
        tmp_path,
        "<para>Use LRU1010. Not LRU10100 or LRU1010-X.</para>"
        "<table><tgroup><tbody><row><entry><para>PN-1</para></entry></row></tbody></tgroup></table>"
        "<para>Use <emphasis>PN-2</emphasis> now</para>"
        "<para>Both <partNumber>PN-3</partNumber> here</para>",
    )
    index = ix.build_index(workspace_for(tmp_path))
    assert len(ix.find_part(index, "LRU1010")) == 1
    assert len(ix.find_part(index, "PN-1")) == 1  # entry and its para: one occurrence
    assert len(ix.find_part(index, "PN-2")) == 1  # inline emphasis belongs to the paragraph
    (pn3,) = ix.find_part(index, "PN-3")
    assert pn3.kind == "partNumber"  # structured only, not counted twice as free text


def test_part_numbers_in_any_element_text_are_found(tmp_path: Path):
    write_dm(
        tmp_path,
        "<itemDescr>See PN-77 here</itemDescr><shortName>PN-78</shortName>"
        "<listItemTerm>PN-79</listItemTerm><definition>use PN-80.</definition>"
        "<caption>PN-81</caption><refs>x</refs>",
    )
    index = ix.build_index(workspace_for(tmp_path))
    for number in ("PN-77", "PN-78", "PN-79", "PN-80", "PN-81"):
        found = ix.find_part(index, number)
        assert [o.kind for o in found] == ["para"], number


def test_titles_are_searched_but_status_boilerplate_is_not(tmp_path: Path):
    xml = (
        "<dmodule><identAndStatusSection><dmAddress><dmIdent><dmCode/></dmIdent>"
        "<dmAddressItems><dmTitle><techName>PN-91 unit</techName></dmTitle></dmAddressItems>"
        "</dmAddress><dmStatus><responsiblePartnerCompany><enterpriseName>PN-90"
        "</enterpriseName></responsiblePartnerCompany></dmStatus></identAndStatusSection>"
        "<content><para>PN-92</para></content></dmodule>"
    )
    name = "DMC-SYNTH-AAA-D00-00-00-00AA-040A-A_001-00_EN-US.XML"
    (tmp_path / name).write_text(xml, encoding="utf-8")
    index = ix.build_index(workspace_for(tmp_path))
    assert len(ix.find_part(index, "PN-91")) == 1  # data module title
    assert len(ix.find_part(index, "PN-92")) == 1
    assert ix.find_part(index, "PN-90") == []  # company name in the status section


def test_keep_docs_keeps_the_parsed_data_modules_only_on_request():
    ws = workspace_for(FIXTURES)
    assert ix.build_index(ws).loaded == {}
    kept = ix.build_index(ws, keep_docs=True)
    assert len(kept.loaded) == 9 and all(k.startswith("fixtures:") for k in kept.loaded)
    assert set(kept.chain_notes) == {k for k, d in kept.docs.items() if d.role in ("dm", "brex")}


# --- internal refs, dm refs, figures ------------------------------------------


def test_internal_references(idx: ix.CorpusIndex):
    expected = {
        "irtt05": ("tool-0001", "supportEquipDescr", "stp-0001"),
        "irtt06": ("spr-0001", "spareDescr", "stp-0002"),
        "irtt04": ("sup-0001", "supplyDescr", "stp-0004"),
    }
    assert set(idx.internal_refs) == set(expected)
    for target_type, (target_id, tag, step) in expected.items():
        (entry,) = idx.internal_refs[target_type]
        assert entry.ref.doc_key == stem(PROCED)
        assert (entry.target_id, entry.target_tag, entry.element_id) == (target_id, tag, step)
        assert entry.xpath.endswith("/internalRef")


def test_internal_reference_to_a_missing_id(tmp_path: Path):
    ref = '<internalRef internalRefId="ghost" internalRefTargetType="irtt01"/>'
    write_dm(tmp_path, f"<para>{ref}</para>")
    index = ix.build_index(workspace_for(tmp_path))
    (entry,) = index.internal_refs["irtt01"]
    assert entry.target_tag is None and entry.target_id == "ghost"


def test_dm_references(idx: ix.CorpusIndex):
    mine = [e for e in idx.dm_refs if e.ref.doc_key == stem(PROCED)]
    assert len(mine) == 1
    assert (mine[0].context_tag, mine[0].target) == ("brexDmRef", PROJECT_KEY)
    assert (mine[0].issue, mine[0].in_work) == ("001", "00")
    upf = [e for e in idx.dm_refs if e.ref.doc_key.startswith("UPF-")]
    assert len(upf) == 2 and {e.context_tag for e in upf} == {"brexDmRef"}


def test_figures(idx: ix.CorpusIndex):
    key = f"fixtures:DMC-RTPROTO-{CODE}-041A-A_001-00_EN-US#fig-0001"
    figure = idx.figures[key]
    assert figure.figure_id == "fig-0001"
    assert figure.graphics == ["ICN-RTPROTO-A-000001-A-00001-A-001-01"]
    assert figure.referenced_by == []


def test_figure_referenced_by_an_internal_ref(tmp_path: Path):
    write_dm(
        tmp_path,
        '<levelledPara id="lp1"><para>See <internalRef internalRefId="fig-1" '
        'internalRefTargetType="irtt01"/>.</para>'
        '<figure id="fig-1"><title>T</title><graphic infoEntityIdent="ICN-A"/>'
        '<graphic infoEntityIdent="ICN-B"/></figure></levelledPara>',
    )
    index = ix.build_index(workspace_for(tmp_path))
    (figure,) = index.figures.values()
    assert figure.graphics == ["ICN-A", "ICN-B"]
    assert figure.referenced_by == ["lp1"]


# --- robustness ---------------------------------------------------------------


def test_unreadable_document_is_recorded_not_fatal(monkeypatch):
    real_load = xio.load

    def flaky(path):
        if "520A" in Path(path).name:
            raise ValueError("boom")
        return real_load(path)

    # Only the index module sees the failing loader (the classifier still reads the file).
    names = {n: getattr(xio, n) for n in dir(xio) if not n.startswith("__")}
    names["load"] = flaky
    monkeypatch.setattr(ix, "xio", types.SimpleNamespace(**names))
    index = ix.build_index(workspace_for(FIXTURES))
    assert list(index.unreadable) == [f"fixtures:{stem(PROCED)}"]
    assert "boom" in index.unreadable[f"fixtures:{stem(PROCED)}"]
    assert index.counts()["fixtures"]["dm"] == 9  # still listed
    assert len(ix.find_part(index, "LRU1010")) == 5  # the other documents are indexed


def test_ref_key():
    from redactech.models import SourceRef

    assert ix.ref_key(SourceRef(source_id="s", doc_key="k")) == "s:k"


# --- real Bike data (skipped when data/ is absent) ----------------------------


def _bike_workspace(repo_root: Path, version: str = "4.1") -> wsmod.Workspace:
    data = repo_root / "data" / f"s1000d-{version}"
    source = wsmod.Source(
        id=f"bike{version.replace('.', '')}",
        path=(data / "bike").resolve(),
        brex_dirs=[(data / "brex").resolve()],
        issue=version,
        schemas_dir=(data / "schemas").resolve(),
    )
    return wsmod.Workspace([source], repo_root)


@pytest.mark.data41
def test_real_bike_41_lru1010_has_four_occurrences_in_three_files(repo_root: Path):
    index = ix.build_index(_bike_workspace(repo_root))
    found = ix.find_part(index, "LRU1010")
    light = "S1000DLIGHTING-AAA-D00-00-00-"
    assert sorted((o.ref.doc_key, o.kind, o.writable) for o in found) == [
        (f"DMC-{light}00AA-00GA-D_001-00_EN-US", "partSpec", True),
        (f"DMC-{light}01AA-941A-D_007-00_EN-US", "partRef", True),
        (f"UPF-{light}00AA-00GA-D_001-00_EN-US", "para", False),
        (f"UPF-{light}00AA-00GA-D_001-00_EN-US", "partIdent", False),
    ]
    assert len({o.ref.doc_key for o in found}) == 3


@pytest.mark.data41
def test_real_bike_41_chains_and_no_unreadable_file(repo_root: Path):
    index = ix.build_index(_bike_workspace(repo_root))
    assert index.unreadable == {}
    dms = [d for d in index.docs.values() if d.role == "dm" and d.ref.doc_key.startswith("DMC-")]
    assert dms
    for doc in dms:
        assert doc.brex_chain, doc.ref.doc_key
        assert doc.brex_chain[-1].doc_key.startswith("DMC-S1000D-E-04-10-0301"), doc.ref.doc_key


@pytest.mark.data42
def test_real_bike_42_lru1010_is_indexed(repo_root: Path):
    index = ix.build_index(_bike_workspace(repo_root, "4.2"))
    assert len(ix.find_part(index, "LRU1010")) == 4
