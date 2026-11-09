"""Tests of redactech.sources.classify."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.models import SourceDoc
from redactech.sources.classify import classify

CODE = "AAA-D00-00-00-00AA"


def fx(model: str, info: str, loc: str, issue: str = "001-00", prefix: str = "DMC") -> str:
    return f"{prefix}-{model}-{CODE}-{info}-{loc}_{issue}_EN-US.XML"


def write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_procedure_fixture_is_a_writable_dm(fixtures_dir: Path):
    doc = classify(fixtures_dir / fx("RTPROTO", "520A", "A"), source_id="fixtures")
    assert isinstance(doc, SourceDoc)
    assert (doc.role, doc.kind, doc.writable) == ("dm", "s1000d", True)
    assert doc.issue == "4.1" and doc.language == "en-US"
    assert doc.ref.source_id == "fixtures"
    assert doc.ref.doc_key == fx("RTPROTO", "520A", "A").removesuffix(".XML")
    assert doc.path.endswith(fx("RTPROTO", "520A", "A"))


@pytest.mark.parametrize("model", ["RTDEFLT", "RTPROTO"])
def test_brex_fixtures_are_not_writable(fixtures_dir: Path, model: str):
    doc = classify(fixtures_dir / fx(model, "022A", "D"))
    assert (doc.role, doc.kind, doc.writable) == ("brex", "s1000d", False)


def test_upf_fixture_is_read_only(fixtures_dir: Path):
    doc = classify(fixtures_dir / fx("RTPROTO", "0A3A", "D", prefix="UPF"))
    assert (doc.role, doc.writable) == ("upf", False)


@pytest.mark.parametrize(
    "info,loc,issue",
    [("041A", "A", "001-00"), ("040A", "A", "001-00"), ("521A", "A", "001-00"),
     ("520B", "A", "007-00"), ("941A", "D", "001-00"), ("0A3A", "D", "001-00")],
)
def test_other_fixtures_are_dms(fixtures_dir: Path, info: str, loc: str, issue: str):
    doc = classify(fixtures_dir / fx("RTPROTO", info, loc, issue))
    assert (doc.role, doc.writable) == ("dm", True)


def test_security_fixtures_never_raise(fixtures_dir: Path):
    for path in sorted((fixtures_dir / "security").glob("*.xml")):
        assert isinstance(classify(path), SourceDoc)


@pytest.mark.parametrize(
    "name", ["ICN-S1000DBIKE-AAA-D000000-0-U8025-00001-A-001-01.PNG", "ICN-X-001-01.cgm"]
)
def test_graphics_are_read_only_icn(tmp_path: Path, name: str):
    doc = classify(write(tmp_path, name, b"\x89PNG"))
    assert (doc.role, doc.kind, doc.writable) == ("icn", "graphic", False)


@pytest.mark.parametrize("ext", [".cgm", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".svg", ".gif"])
def test_graphic_extensions_without_icn_name(tmp_path: Path, ext: str):
    doc = classify(write(tmp_path, f"picture{ext}", b"data"))
    assert (doc.role, doc.kind, doc.writable) == ("icn", "graphic", False)


def test_pm_and_ddn_and_update_roots(tmp_path: Path):
    pm = classify(write(tmp_path, "PMC-X-C0419-00001-00_001-00_EN-US.XML", b"<pm/>"))
    assert (pm.role, pm.kind, pm.language) == ("pm", "s1000d", "EN-US")
    ddn = classify(write(tmp_path, "DDN-X-C3002-U8025-2012-00001.XML", b"<ddn/>"))
    assert (ddn.role, ddn.kind) == ("ddn", "s1000d")
    upf = classify(write(tmp_path, "something.XML", b"<dataUpdateFile/>"))
    assert (upf.role, upf.writable) == ("upf", False)


def test_dm_root_wins_over_the_file_name_prefix(tmp_path: Path):
    doc = classify(write(tmp_path, "DME-SF518-X_008-00_EN-US.XML", b"<dmodule/>"))
    assert doc.role == "dm"


def test_unknown_xml_is_other_with_kind_xml(tmp_path: Path):
    doc = classify(write(tmp_path, "metadata.xml", b"<icnMetadataFile/>"))
    assert (doc.role, doc.kind) == ("other", "xml")


@pytest.mark.parametrize(
    "name,content",
    [
        ("DMC-X-AAA-D00-00-00-00AA-040A-A_001-00_EN-US.XML", b"<not xml"),
        ("garbled.xml", b"\x00\xff\xfe<<<>>>"),
        ("empty.xml", b""),
        ("notes.txt", b"hello"),
        ("data.bin", b"\x00\x01"),
    ],
)
def test_garbled_or_unknown_files_are_other(tmp_path: Path, name: str, content: bytes):
    doc = classify(write(tmp_path, name, content))
    assert doc.role == "other"


def test_garbled_update_file_stays_read_only(tmp_path: Path):
    doc = classify(write(tmp_path, "UPF-X-AAA-D00-00-00-00AA-0A3A-D_001-00_EN-US.XML", b"<oops"))
    assert (doc.role, doc.writable) == ("upf", False)


def test_missing_file_does_not_raise(tmp_path: Path):
    doc = classify(tmp_path / "does-not-exist.xml")
    assert doc.role == "other"
    assert classify(tmp_path / "ICN-MISSING-001-01.CGM").role == "icn"
