"""Tests of tools/setup_data.py on small synthetic archives."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import setup_data  # noqa: E402


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    path.write_bytes(_zip_bytes(files))


def make_archives(root: Path, extra_bike_41: dict[str, bytes] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base41 = "S1000D Issue 4.1/Issue 4.1"
    bike_inner = {
        "S1000D_4-1_Bike_Samples/DMC-BIKE-AAA-D00-00-00-00AA-022A-D_008-00_EN-US.XML": b"<b41/>",
        "S1000D_4-1_Bike_Samples/DMC-BIKE-AAA-D00-00-00-00AA-040A-A_001-00_EN-US.XML": b"<d41/>",
        "S1000D_4-1_Bike_Samples/ICN-BIKE-0001.cgm": b"cgm",
        **(extra_bike_41 or {}),
    }
    brex_inner = {
        "DMC-DEF-E-04-10-0301-00A-022A-D_009-00_EN-US.XML": b"<def41/>",
        "DMC-DEF-E-04-10-0301-00A-022A-D_009-00_EN-US.html": b"<html/>",
        "logo.jpg": b"jpg",
    }
    _write_zip(
        root / "S1000D Issue 4.1.zip",
        {
            f"{base41}/Bike data set/S1000D_4-1_Bike_Samples.zip": _zip_bytes(bike_inner),
            f"{base41}/Default BREX data module/S1000D_4.1_Default_BREX.zip": _zip_bytes(
                brex_inner
            ),
            f"{base41}/xml_schema_flat/proced.xsd": b"<xsd1/>",
            f"{base41}/xml_schema_flat/comrep.xsd": b"<xsd2/>",
            f"{base41}/Data Dictionary/Files/xml_schema_flat/decoy.xsd": b"decoy",
            f"{base41}/Patches/Patch 4.1.A/xml_schema_flat/decoy2.xsd": b"decoy",
            f"{base41}/Specification/spec.zip": b"ignored",
        },
    )
    base42 = "S1000D Issue 4.2"
    bike42 = f"{base42}/Bike Sample Data Set/Bike Data Set for Issue 4.2"
    default42 = _zip_bytes({"DMC-DEF-F-04-10-0301-00A-022A-D_002-00_EN-US.XML": b"<def42/>"})
    _write_zip(
        root / "S1000D Issue 4.2.zip",
        {
            f"{bike42}/DMC-BIKE-AAA-D00-00-00-00AA-022A-D_009-00_en-US.XML": b"<b42/>",
            f"{bike42}/DMC-BIKE-AAA-D00-00-00-00AA-040A-A_002-00_en-US.XML": b"<d42/>",
            f"{bike42}/ICN-BIKE-0001.cgm": b"cgm",
            f"{base42}/Default BREX Data Module/DMC-DEF-F-022A-D_001-00_EN-US.zip": default42,
            f"{base42}/XML Schema Package/xml_schema_flat/proced.xsd": b"<xsd42/>",
            f"{base42}/Patches/Patch 4.2.B/Bike Data Set for Release number 4.2/"
            "DMC-PATCH-AAA-022A-D_001-00_en-US.XML": b"decoy",
        },
    )
    return root


def names(path: Path) -> set[str]:
    return {p.name for p in path.iterdir()} if path.is_dir() else set()


def test_extracts_expected_layout(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    data = tmp_path / "data"
    summary = setup_data.run(arch, data)
    assert len(names(data / "s1000d-4.1/bike")) == 3
    assert "ICN-BIKE-0001.cgm" in names(data / "s1000d-4.1/bike")
    assert names(data / "s1000d-4.1/brex") == {
        "DMC-BIKE-AAA-D00-00-00-00AA-022A-D_008-00_EN-US.XML",
        "DMC-DEF-E-04-10-0301-00A-022A-D_009-00_EN-US.XML",
    }
    assert names(data / "s1000d-4.1/schemas") == {"proced.xsd", "comrep.xsd"}
    assert len(names(data / "s1000d-4.2/bike")) == 3
    assert names(data / "s1000d-4.2/brex") == {
        "DMC-BIKE-AAA-D00-00-00-00AA-022A-D_009-00_en-US.XML",
        "DMC-DEF-F-04-10-0301-00A-022A-D_002-00_EN-US.XML",
    }
    assert names(data / "s1000d-4.2/schemas") == {"proced.xsd"}
    assert summary["s1000d-4.1/bike"]["new"] == 3
    assert summary["s1000d-4.2/brex"]["new"] == 2


def test_bike_brex_stays_in_bike_too(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    data = tmp_path / "data"
    setup_data.run(arch, data)
    assert (data / "s1000d-4.1/bike/DMC-BIKE-AAA-D00-00-00-00AA-022A-D_008-00_EN-US.XML").is_file()


def test_zip_slip_refused_and_nothing_written(tmp_path: Path):
    arch = make_archives(tmp_path / "arch", {"S1000D_4-1_Bike_Samples/../../evil.txt": b"x"})
    data = tmp_path / "data"
    with pytest.raises(setup_data.UnsafeArchiveError):
        setup_data.run(arch, data)
    assert not data.exists()
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.parametrize("name", ["/abs.txt", "C:/abs.txt", "a/../b.txt", "a\\..\\b.txt"])
def test_check_member_rejects_unsafe_names(name: str):
    with pytest.raises(setup_data.UnsafeArchiveError):
        setup_data.check_member(name)


@pytest.mark.parametrize("name", ["a/b:stream.txt", "dir:x/file.txt", "a/C:/x.txt"])
def test_check_member_rejects_colon_in_any_part(name: str):
    with pytest.raises(setup_data.UnsafeArchiveError):
        setup_data.check_member(name)


def test_duplicate_base_names_are_refused(tmp_path: Path, capsys):
    dup = {
        "S1000D_4-1_Bike_Samples/a/DMC-X-040A-A_001-00_EN-US.XML": b"<one/>",
        "S1000D_4-1_Bike_Samples/b/DMC-X-040A-A_001-00_EN-US.XML": b"<two/>",
    }
    arch = make_archives(tmp_path / "arch", dup)
    data = tmp_path / "data"
    with pytest.raises(setup_data.UnsafeArchiveError):
        setup_data.run(arch, data)
    assert not data.exists()
    code = setup_data.main(["--archives-dir", str(arch), "--data-dir", str(data)])
    assert code == 2
    assert "refused" in capsys.readouterr().out


def test_plan_destinations_stay_inside_the_target(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    plan = setup_data.build_plan(arch / "S1000D Issue 4.1.zip", "4.1", tmp_path / "data")
    root = (tmp_path / "data").resolve()
    assert plan.items
    assert all(root in dest.resolve().parents for dest in plan.items)


def test_check_member_accepts_normal_names():
    setup_data.check_member("S1000D Issue 4.1/Issue 4.1/Bike data set/x.zip")


def test_idempotent(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    data = tmp_path / "data"
    setup_data.run(arch, data)
    target = data / "s1000d-4.1/schemas/proced.xsd"
    mtime = target.stat().st_mtime_ns
    summary = setup_data.run(arch, data)
    assert target.stat().st_mtime_ns == mtime
    assert all(c["new"] == 0 and c["updated"] == 0 for c in summary.values())
    assert summary["s1000d-4.1/bike"]["unchanged"] == 3


def test_changed_file_is_updated(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    data = tmp_path / "data"
    setup_data.run(arch, data)
    target = data / "s1000d-4.1/schemas/proced.xsd"
    target.write_bytes(b"locally modified")
    summary = setup_data.run(arch, data)
    assert summary["s1000d-4.1/schemas"]["updated"] == 1
    assert target.read_bytes() == b"<xsd1/>"


def test_dry_run_writes_nothing(tmp_path: Path, capsys):
    arch = make_archives(tmp_path / "arch")
    data = tmp_path / "data"
    assert setup_data.main(["--archives-dir", str(arch), "--data-dir", str(data), "--dry-run"]) == 0
    assert not data.exists()
    out = capsys.readouterr().out
    assert "dry run" in out and "s1000d-4.1/bike: 3 new" in out


def test_archives_are_not_modified(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in arch.glob("*.zip")}
    setup_data.run(arch, tmp_path / "data")
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in arch.glob("*.zip")}
    assert before == after


def test_missing_archives_exit_code(tmp_path: Path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert setup_data.main(["--archives-dir", str(empty), "--data-dir", str(tmp_path / "d")]) == 1
    assert "no archive found" in capsys.readouterr().out


def test_only_one_archive_present(tmp_path: Path):
    arch = make_archives(tmp_path / "arch")
    (arch / "S1000D Issue 4.2.zip").unlink()
    data = tmp_path / "data"
    setup_data.run(arch, data)
    assert (data / "s1000d-4.1").is_dir() and not (data / "s1000d-4.2").exists()
