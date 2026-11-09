"""Tests of redactech.s1000d.validate."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.s1000d import io as xio
from redactech.s1000d import validate

PROCED = "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML"
FIGURE = "DMC-RTPROTO-AAA-D00-00-00-00AA-041A-A_001-00_EN-US.XML"
VIOLATING = "DMC-RTPROTO-AAA-D00-00-00-00AA-521A-A_001-00_EN-US.XML"
UPF = "UPF-RTPROTO-AAA-D00-00-00-00AA-0A3A-D_001-00_EN-US.XML"

XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
MINI_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="dmodule">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="identAndStatusSection" type="xs:string"/>
        <xs:element name="content" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


def mini_doc(body: str, schema: str = "mini.xsd") -> xio.XmlDoc:
    location = f"http://www.s1000d.org/S1000D_4-1/xml_schema_flat/{schema}"
    xml = f'<dmodule {XSI} xsi:noNamespaceSchemaLocation="{location}">{body}</dmodule>'
    return xio.load_bytes(xml.encode())


@pytest.fixture
def schemas(tmp_path: Path) -> Path:
    folder = tmp_path / "schemas"
    folder.mkdir()
    (folder / "mini.xsd").write_text(MINI_XSD, encoding="utf-8")
    return folder


def load(fixtures_dir: Path, name: str) -> xio.XmlDoc:
    return xio.load(fixtures_dir / name)


def failures(results):
    return [r for r in results if not r.ok]


# --- schema lookup ----------------------------------------------------------------------------


def test_schema_for_maps_the_url_file_name_into_the_local_folder(schemas: Path):
    doc = mini_doc("<identAndStatusSection/><content/>")
    assert validate.schema_for(doc, schemas) == schemas / "mini.xsd"


def test_schema_for_is_none_when_missing_or_unspecified(schemas: Path, tmp_path: Path):
    assert validate.schema_for(mini_doc("", "absent.xsd"), schemas) is None
    assert validate.schema_for(xio.load_bytes(b"<dmodule/>"), schemas) is None
    assert validate.schema_for(mini_doc(""), tmp_path / "no-such-folder") is None


def test_schemas_dir_for_uses_the_detected_issue(tmp_path: Path):
    doc = mini_doc("")
    assert validate.schemas_dir_for(doc, tmp_path) is None
    folder = tmp_path / "s1000d-4.1" / "schemas"
    folder.mkdir(parents=True)
    assert validate.schemas_dir_for(doc, tmp_path) == folder
    assert validate.schemas_dir_for(xio.load_bytes(b"<dmodule/>"), tmp_path) is None


def test_load_schema_is_cached_per_path(schemas: Path):
    first = validate.load_schema(schemas / "mini.xsd")
    assert validate.load_schema(schemas / "mini.xsd") is first


# --- XSD ------------------------------------------------------------------------------------------


def test_valid_document_passes_the_xsd(schemas: Path):
    body = "<identAndStatusSection>a</identAndStatusSection><content>b</content>"
    results = validate.check_xsd(mini_doc(body), schemas)
    assert len(results) == 1
    assert results[0].ok and results[0].name == "xsd" and results[0].severity == "info"


def test_invalid_document_gives_one_result_per_error(schemas: Path):
    doc = mini_doc("<identAndStatusSection/><unknownElement/><content/>")
    results = validate.check_xsd(doc, schemas)
    assert results and all(not r.ok for r in results)
    assert all(r.name == "xsd" and r.severity == "error" for r in results)
    assert any("unknownElement" in r.details for r in results)
    assert all(r.details.startswith("line ") for r in results)


def test_missing_schema_is_a_single_warning(fixtures_dir: Path, tmp_path: Path):
    results = validate.check_xsd(load(fixtures_dir, PROCED), tmp_path)
    assert len(results) == 1
    assert (results[0].ok, results[0].severity, results[0].name) == (False, "warning", "xsd")
    assert "schema not found" in results[0].details


def test_broken_schema_is_a_warning_not_a_crash(tmp_path: Path):
    folder = tmp_path / "schemas"
    folder.mkdir()
    (folder / "mini.xsd").write_text("<not-a-schema/>", encoding="utf-8")
    results = validate.check_xsd(mini_doc(""), folder)
    assert len(results) == 1 and results[0].severity == "warning" and not results[0].ok


def test_result_ref_uses_the_file_stem(fixtures_dir: Path, tmp_path: Path):
    result = validate.check_xsd(load(fixtures_dir, PROCED), tmp_path)[0]
    assert result.ref.doc_key == PROCED.removesuffix(".XML")


# --- integrity ------------------------------------------------------------------------------------


def test_valid_fixtures_pass_integrity(fixtures_dir: Path):
    for path in sorted(fixtures_dir.glob("DMC-*.XML")):
        results = validate.check_integrity(xio.load(path))
        assert [r.ok for r in results] == [True], path.name


def test_update_file_fails_integrity(fixtures_dir: Path):
    results = validate.check_integrity(load(fixtures_dir, UPF))
    assert len(results) == 1 and not results[0].ok and "dataUpdateFile" in results[0].details


def test_missing_sections_are_reported():
    results = validate.check_integrity(xio.load_bytes(b"<dmodule><content/></dmodule>"))
    assert [r.details for r in results] == ["missing identAndStatusSection"]
    results = validate.check_integrity(xio.load_bytes(b"<dmodule/>"))
    assert len(failures(results)) == 2


# --- ids ----------------------------------------------------------------------------------------


def test_fixture_ids_are_unique(fixtures_dir: Path):
    for path in sorted(fixtures_dir.glob("DMC-*.XML")):
        assert failures(validate.check_ids(xio.load(path))) == [], path.name


def test_duplicate_id_is_reported_once_with_its_xpath():
    doc = xio.load_bytes(b'<r><p id="a"/><p id="b"/><p id="a"/><p id="a"/></r>')
    results = validate.check_ids(doc)
    assert len(results) == 1
    assert not results[0].ok and results[0].name == "ids"
    assert "'a'" in results[0].details and "3 times" in results[0].details
    assert results[0].xpath == "/r/p[3]"


def test_duplicate_id_in_a_fixture_is_found(fixtures_dir: Path):
    doc = load(fixtures_dir, PROCED)
    steps = list(doc.root.iter("proceduralStep"))
    steps[1].set("id", steps[0].get("id"))
    results = validate.check_ids(doc)
    assert len(results) == 1 and "stp-0001" in results[0].details


# --- links --------------------------------------------------------------------------------------


def test_fixture_internal_references_resolve(fixtures_dir: Path):
    results = validate.check_links(load(fixtures_dir, PROCED))
    assert [r.ok for r in results] == [True]


def test_broken_internal_ref_is_reported(fixtures_dir: Path):
    doc = load(fixtures_dir, PROCED)
    ref = next(doc.root.iter("internalRef"))
    ref.set("internalRefId", "does-not-exist")
    results = validate.check_links(doc)
    assert len(results) == 1 and not results[0].ok
    assert "does-not-exist" in results[0].details
    assert results[0].xpath and "internalRef" in results[0].xpath


def test_known_ids_replace_the_collected_ids():
    doc = xio.load_bytes(b'<r><internalRef internalRefId="x"/></r>')
    assert failures(validate.check_links(doc)) != []
    assert failures(validate.check_links(doc, known_ids={"x"})) == []


def test_internal_ref_without_target_is_reported():
    doc = xio.load_bytes(b"<r><internalRef/></r>")
    assert len(failures(validate.check_links(doc))) == 1


# --- ICN ----------------------------------------------------------------------------------------


def test_figure_fixture_icn_is_declared(fixtures_dir: Path):
    doc = load(fixtures_dir, FIGURE)
    assert "ICN-RTPROTO-A-000001-A-00001-A-001-01" in validate.declared_entities(doc)
    assert [r.ok for r in validate.check_icn(doc)] == [True]


UNDECLARED = (
    b'<?xml version="1.0"?>\n<!DOCTYPE dmodule []>\n'
    b'<dmodule><content><graphic infoEntityIdent="ICN-X-001-01"/></content></dmodule>'
)


def test_undeclared_icn_is_a_warning():
    results = validate.check_icn(xio.load_bytes(UNDECLARED))
    assert len(results) == 1 and not results[0].ok
    assert (results[0].name, results[0].severity) == ("icn", "warning")
    assert "ICN-X-001-01" in results[0].details


def test_icn_file_in_the_source_folder_is_enough(tmp_path: Path):
    (tmp_path / "ICN-X-001-01.CGM").write_bytes(b"cgm")
    results = validate.check_icn(xio.load_bytes(UNDECLARED), source_dir=tmp_path)
    assert [r.ok for r in results] == [True]


def test_document_without_graphics_passes_icn(fixtures_dir: Path):
    assert [r.ok for r in validate.check_icn(load(fixtures_dir, PROCED))] == [True]


# --- check_all ------------------------------------------------------------------------------------


def test_check_all_combines_every_check(fixtures_dir: Path, tmp_path: Path):
    results = validate.check_all(load(fixtures_dir, PROCED), tmp_path)
    assert [r.name for r in results] == ["xsd", "integrity", "ids", "links", "icn"]
    assert [r.ok for r in results] == [False, True, True, True, True]  # xsd: schema not found


# --- real schemas (skipped when data/ is absent) -------------------------------------------------


def _bike_dms(repo_root: Path, version: str) -> list[Path]:
    folder = repo_root / "data" / f"s1000d-{version}" / "bike"
    return sorted(folder.glob("DMC-*.XML"))


@pytest.mark.data41
def test_valid_fixtures_pass_the_real_41_schemas(repo_root: Path, fixtures_dir: Path):
    schemas = repo_root / "data" / "s1000d-4.1" / "schemas"
    for path in sorted(fixtures_dir.glob("DMC-*.XML")):
        if path.name == VIOLATING:
            continue
        errors = failures(validate.check_xsd(xio.load(path), schemas))
        assert errors == [], (path.name, [e.details for e in errors][:3])


@pytest.mark.data41
def test_violating_fixture_fails_the_real_41_schema(repo_root: Path, fixtures_dir: Path):
    schemas = repo_root / "data" / "s1000d-4.1" / "schemas"
    results = validate.check_xsd(load(fixtures_dir, VIOLATING), schemas)
    assert any(r.severity == "error" and "unknownElement" in r.details for r in results)


@pytest.mark.data41
def test_bike_41_against_its_schemas_is_recorded(repo_root: Path):
    """Pre-existing XSD errors of the public data are counted, never turned into failures."""
    schemas = repo_root / "data" / "s1000d-4.1" / "schemas"
    paths = _bike_dms(repo_root, "4.1")
    assert paths
    invalid = 0
    for path in paths:
        results = validate.check_xsd(xio.load(path), schemas)
        assert results, path.name
        assert not [r for r in results if r.severity == "warning"], (path.name, results[0].details)
        invalid += any(not r.ok for r in results)
    print(f"Bike 4.1: {len(paths)} DMs, {invalid} with pre-existing XSD errors")
