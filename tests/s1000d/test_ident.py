"""Tests of redactech.s1000d.ident (DMC, issue info, Issue detection, file names)."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from redactech.s1000d import ident
from redactech.s1000d import io as xio

PROCED = "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML"

# Names taken from the public Bike data sets (Issue 4.1 and 4.2) and the synthetic fixtures.
REAL_NAMES = [
    "DMC-S1000DBIKE-AAA-D00-00-00-00AA-00PA-D_005-00_EN-US.XML",
    "DMC-BRAKE-AAA-D00-00-00-00AA-00WA-D_001-00_EN-US.XML",
    "DMC-S1000DBIKE-AAA-DA1-10-00-00AA-251A-A_007-00_EN-US.XML",
    "DMC-S1000DBIKE-AAA-D00-00-00-00AA-952A-T-H31A_002-00_EN-US.XML",
    "DMC-S1000DBIKE-AAA-D00-00-00-00AA-022A-D_009-00_en-US.XML",
    "DME-SF518-CE0701-S1000DBIKE-AAA-D00-00-00-00AA-131A-A_008-00_EN-US.XML",
    "DML-S1000DBIKE-C3002-C-2012-00001_001-01.XML",
    "DDN-S1000DBIKE-C3002-U8025-2012-00001.XML",
    "DDN-S1000DBIKE-B6865-B6865-2016_00001.XML",
    "PMC-BRAKE-C3002-EPWG1-00_000-01_EN-US.XML",
    "PMC-BRAKE-B6865-EPWG1-00_001-00_en-US.XML",
    "UPF-S1000DLIGHTING-AAA-D00-00-00-00AA-00GA-D_001-00_EN-US.XML",
    "IMF-C0419-S1000D0360-001-01_001-00.XML",
    "ICN-S1000DBIKE-AAA-D000000-0-U8025-00001-A-001-01.PNG",
    "ICN-C0419-S1000D0358-001-01.CGM",
    "ICN-S1000DBIKE-AAA-DA00000-A-06RT9-00094-A-001-01.GIF",
]


def dmcode_element(**overrides: str) -> etree._Element:
    attrs = {
        "modelIdentCode": "S1000DBIKE",
        "systemDiffCode": "AAA",
        "systemCode": "DA1",
        "subSystemCode": "1",
        "subSubSystemCode": "0",
        "assyCode": "00",
        "disassyCode": "00",
        "disassyCodeVariant": "AA",
        "infoCode": "251",
        "infoCodeVariant": "A",
        "itemLocationCode": "A",
        **overrides,
    }
    return etree.Element("dmCode", attrs)


def fixture_doc(fixtures_dir: Path, name: str = PROCED) -> xio.XmlDoc:
    return xio.load(fixtures_dir / name)


# --- DmCode -----------------------------------------------------------------------------------


def test_dmc_string_from_attributes():
    code = ident.DmCode.from_element(dmcode_element())
    assert code.dmc_string() == "S1000DBIKE-AAA-DA1-10-00-00AA-251A-A"
    assert code.model_ident_code == "S1000DBIKE" and code.info_code == "251"


def test_dmc_string_with_learning_codes():
    code = ident.DmCode.from_element(
        dmcode_element(
            systemCode="D00",
            subSystemCode="0",
            infoCode="952",
            learnCode="H31",
            learnEventCode="A",
            itemLocationCode="T",
        )
    )
    assert code.dmc_string() == "S1000DBIKE-AAA-D00-00-00-00AA-952A-T-H31A"


def test_dm_code_of_fixtures(fixtures_dir: Path):
    code = ident.dm_code(fixture_doc(fixtures_dir))
    assert code.dmc_string() == "RTPROTO-AAA-D00-00-00-00AA-520A-A"


def test_dm_code_none_for_non_data_module(fixtures_dir: Path):
    upf = fixture_doc(fixtures_dir, "UPF-RTPROTO-AAA-D00-00-00-00AA-0A3A-D_001-00_EN-US.XML")
    assert ident.dm_code(upf) is None
    assert ident.issue_info(upf) is None
    assert ident.language(upf) is None


def test_dmc_string_matches_every_fixture_file_name(fixtures_dir: Path):
    for path in sorted(fixtures_dir.glob("DMC-*.XML")):
        doc = xio.load(path)
        parsed = ident.parse_filename(path.name)
        assert ident.dm_code(doc).dmc_string() == parsed.code, path.name


# --- issue info, language, Issue ---------------------------------------------------------------


def test_issue_info_and_language(fixtures_dir: Path):
    assert ident.issue_info(fixture_doc(fixtures_dir)) == ("001", "00")
    assert ident.language(fixture_doc(fixtures_dir)) == ("en", "US")
    marks = fixture_doc(fixtures_dir, "DMC-RTPROTO-AAA-D00-00-00-00AA-520B-A_007-00_EN-US.XML")
    assert ident.issue_info(marks) == ("007", "00")


def test_detect_issue_from_fixtures(fixtures_dir: Path):
    for path in sorted(fixtures_dir.glob("*.XML")):
        assert ident.detect_issue(xio.load(path)) == "4.1", path.name


XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'


def detect(attribute: str, value: str | None) -> str | None:
    attr = f'xsi:{attribute}="{value}"' if value is not None else ""
    return ident.detect_issue(xio.load_bytes(f"<dmodule {XSI} {attr}/>".encode()))


def test_detect_issue_rules():
    base = "http://www.s1000d.org"
    no_ns = "noNamespaceSchemaLocation"
    assert detect(no_ns, f"{base}/S1000D_4-2/xml_schema_flat/proced.xsd") == "4.2"
    assert detect(no_ns, f"{base}/S1000D_4-1/xml_schema_flat/brex.xsd") == "4.1"
    assert detect("schemaLocation", f"urn:x {base}/S1000D_4-2/xml_schema_flat/ipd.xsd") == "4.2"
    assert detect(no_ns, f"{base}/S1000D_5-0/xml_schema_flat/a.xsd") is None
    assert detect(no_ns, "http://example.org/other.xsd") is None
    assert detect(no_ns, None) is None


def test_is_brex(fixtures_dir: Path):
    default = "DMC-RTDEFLT-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"
    project = "DMC-RTPROTO-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"
    assert ident.is_brex(fixture_doc(fixtures_dir, default))
    assert ident.is_brex(fixture_doc(fixtures_dir, project))
    assert not ident.is_brex(fixture_doc(fixtures_dir))
    assert not ident.is_brex(xio.load_bytes(b"<dmodule/>"))


# --- file names -----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", REAL_NAMES)
def test_filename_round_trip_on_real_names(name: str):
    parsed = ident.parse_filename(name)
    assert parsed is not None, name
    assert ident.build_filename(parsed) == name


def test_parse_filename_parts():
    parsed = ident.parse_filename("DMC-S1000DBIKE-AAA-D00-00-00-00AA-00PA-D_005-00_EN-US.XML")
    assert parsed == ident.FileName(
        prefix="DMC", code="S1000DBIKE-AAA-D00-00-00-00AA-00PA-D", issue="005", in_work="00",
        language="EN", country="US", extension="XML",
    )
    lower = ident.parse_filename("dmc-X-Y_002-01_en-US.xml")
    assert (lower.prefix, lower.code) == ("DMC", "X-Y")
    assert (lower.language, lower.extension) == ("en", "xml")
    ddn = ident.parse_filename("DDN-S1000DBIKE-C3002-U8025-2012-00001.XML")
    assert ddn.issue is None and ddn.language is None
    dml = ident.parse_filename("DML-S1000DBIKE-C3002-C-2012-00001_001-01.XML")
    assert (dml.issue, dml.in_work, dml.language) == ("001", "01", None)
    ddn42 = ident.parse_filename("DDN-S1000DBIKE-B6865-B6865-2016_00001.XML")
    assert ddn42.code == "S1000DBIKE-B6865-B6865-2016_00001" and ddn42.issue is None
    pmc = ident.parse_filename("PMC-BRAKE-C3002-EPWG1-00_000-01_EN-US.XML")
    assert (pmc.issue, pmc.in_work) == ("000", "01")


def test_parse_filename_accepts_a_path():
    path = Path("some") / "dir" / "DMC-A-B_001-00_EN-US.XML"
    assert ident.parse_filename(str(path)).code == "A-B"


@pytest.mark.parametrize("name", ["notes.txt", "README.md", "DMC.XML", "image.png", ""])
def test_parse_filename_rejects_other_names(name: str):
    assert ident.parse_filename(name) is None


def test_build_filename_explicit():
    fn = ident.FileName("DMC", "A-B", "003", "02", "EN", "US", "XML")
    assert ident.build_filename(fn) == "DMC-A-B_003-02_EN-US.XML"


def test_filename_for_every_fixture(fixtures_dir: Path):
    for path in sorted(fixtures_dir.glob("DMC-*.XML")):
        doc = xio.load(path)
        issue, in_work = ident.issue_info(doc)
        assert ident.filename_for(doc, issue, in_work) == path.name


def test_filename_for_new_numbers_and_case_style(fixtures_dir: Path):
    raw = (fixtures_dir / PROCED).read_bytes()
    named = xio.load_bytes(raw, Path("DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_en-US.xml"))
    assert ident.filename_for(named, 2, 0) == (
        "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_002-00_en-US.xml"
    )
    anonymous = xio.load_bytes(raw)
    assert ident.filename_for(anonymous, "3", "4") == (
        "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_003-04_EN-US.XML"
    )


def test_filename_for_requires_a_data_module(fixtures_dir: Path):
    upf = fixture_doc(fixtures_dir, "UPF-RTPROTO-AAA-D00-00-00-00AA-0A3A-D_001-00_EN-US.XML")
    with pytest.raises(ValueError):
        ident.filename_for(upf, 1, 0)


# --- real Bike data (skipped when data/ is absent) ----------------------------------------


def _check_real(repo_root: Path, version: str, expected_issue: str) -> None:
    folder = repo_root / "data" / f"s1000d-{version}" / "bike"
    names = sorted(p for p in folder.iterdir() if p.name.upper().startswith("DMC-"))
    assert names
    for path in names:
        parsed = ident.parse_filename(path.name)
        assert parsed is not None, path.name
        assert ident.build_filename(parsed) == path.name
        doc = xio.load(path)
        assert ident.dm_code(doc).dmc_string() == parsed.code, path.name
        assert ident.issue_info(doc) == (parsed.issue, parsed.in_work), path.name
        assert ident.detect_issue(doc) == expected_issue, path.name


@pytest.mark.data41
def test_real_bike_41(repo_root: Path):
    _check_real(repo_root, "4.1", "4.1")


@pytest.mark.data42
def test_real_bike_42(repo_root: Path):
    _check_real(repo_root, "4.2", "4.2")
