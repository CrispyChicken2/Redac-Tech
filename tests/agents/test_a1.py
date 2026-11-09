"""Tests of redactech.agents.a1_indexer (index + baseline of pre-existing problems)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from redactech.agents import a1_indexer
from redactech.s1000d import validate
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
VIOLATING = f"DMC-RTPROTO-{CODE}-521A-A_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"

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
        <xs:element name="content">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="procedure">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="preliminaryRqmts" type="anyContent"/>
                    <xs:element name="mainProcedure">
                      <xs:complexType>
                        <xs:sequence>
                          <xs:element name="proceduralStep" type="anyContent"
                                      maxOccurs="unbounded"/>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>
                    <xs:element name="closeRqmts" type="anyContent"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


def stem(name: str) -> str:
    return name.removesuffix(".XML")


def fixture_workspace(folder: Path = FIXTURES, **overrides) -> wsmod.Workspace:
    folder = folder.resolve()
    values = {"id": "fixtures", "path": folder, "brex_dirs": [folder], "issue": "4.1"}
    return wsmod.Workspace([wsmod.Source(**{**values, **overrides})], folder)


def copy_into(folder: Path, *names: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy(FIXTURES / name, folder / name)
    return folder


# --- fixtures workspace (no schemas folder) -----------------------------------


def test_only_the_violating_fixture_has_problems():
    index, results = a1_indexer.run(fixture_workspace())
    found = a1_indexer.problems(results)
    assert {r.ref.doc_key for r in found} == {stem(VIOLATING)}
    (brex_error,) = found
    assert (brex_error.name, brex_error.severity) == ("brex", "error")
    assert brex_error.rule["xpath"] == "//proceduralStep/note"
    assert index.counts()["fixtures"]["dm"] == 9


def test_every_result_is_marked_pre_existing_and_belongs_to_a_dm():
    index, results = a1_indexer.run(fixture_workspace())
    assert results and {r.origin for r in results} == {"pre_existing"}
    dm_keys = {d.ref.doc_key for d in index.docs.values() if d.role == "dm"}
    assert {r.ref.doc_key for r in results} == dm_keys  # BREX and update files are not checked


def test_run_does_not_keep_the_parsed_documents():
    index, _ = a1_indexer.run(fixture_workspace())
    assert index.loaded == {}


def test_checks_that_find_nothing_are_ok_results_not_problems():
    _, results = a1_indexer.run(fixture_workspace())
    mine = [r for r in results if r.ref.doc_key == stem(PROCED)]
    assert {r.name for r in mine} == {"xsd", "integrity", "ids", "links", "icn", "brex"}
    assert all(r.ok for r in mine)
    skipped = next(r for r in mine if r.name == "xsd")
    assert "skipped" in skipped.details


def test_problems_helper_keeps_only_failures():
    _, results = a1_indexer.run(fixture_workspace())
    assert all(not r.ok for r in a1_indexer.problems(results))
    assert len(a1_indexer.problems(results)) < len(results)


# --- XSD baseline with a tiny schema ------------------------------------------


def schema_workspace(tmp_path: Path) -> wsmod.Workspace:
    bike = copy_into(tmp_path / "s1000d-4.1" / "bike", PROCED, VIOLATING, PROJECT, DEFAULT)
    schemas = tmp_path / "s1000d-4.1" / "schemas"
    schemas.mkdir()
    (schemas / "proced.xsd").write_text(MINI_PROCED_XSD, encoding="utf-8")
    return fixture_workspace(bike, schemas_dir=schemas.resolve())


def test_violating_fixture_has_pre_existing_xsd_and_brex_errors(tmp_path: Path):
    _, results = a1_indexer.run(schema_workspace(tmp_path))
    found = a1_indexer.problems(results)
    by_doc: dict[str, set[str]] = {}
    for r in found:
        by_doc.setdefault(r.ref.doc_key, set()).add(r.name)
    assert by_doc == {stem(VIOLATING): {"xsd", "brex"}}
    xsd = [r for r in found if r.name == "xsd"]
    assert xsd and all(r.origin == "pre_existing" and r.severity == "error" for r in xsd)
    assert any("unknownElement" in r.details for r in xsd)


def test_clean_fixture_passes_the_schema(tmp_path: Path):
    _, results = a1_indexer.run(schema_workspace(tmp_path))
    xsd = [r for r in results if r.name == "xsd" and r.ref.doc_key == stem(PROCED)]
    assert len(xsd) == 1 and xsd[0].ok and "valid" in xsd[0].details


# --- robustness ---------------------------------------------------------------


def test_missing_brex_gives_pre_existing_warnings(tmp_path: Path):
    folder = copy_into(tmp_path / "only-dm", PROCED)
    _, results = a1_indexer.run(fixture_workspace(folder))
    found = a1_indexer.problems(results)
    assert {(r.name, r.severity, r.origin) for r in found} == {("brex", "warning", "pre_existing")}
    assert len(found) == 2  # chain resolution note + "no BREX to check against"
    assert all(r.ref.doc_key == stem(PROCED) for r in found)


def test_one_failing_check_becomes_an_integrity_error_and_the_run_goes_on(monkeypatch):
    real = validate.check_ids

    def flaky(doc, ref=None):
        if "520A" in doc.path.name:
            raise RuntimeError("boom")
        return real(doc, ref)

    monkeypatch.setattr(validate, "check_ids", flaky)
    _, results = a1_indexer.run(fixture_workspace())
    found = a1_indexer.problems(results)
    errors = [r for r in found if r.ref.doc_key == stem(PROCED)]
    assert len(errors) == 1
    assert (errors[0].name, errors[0].severity, errors[0].origin) == (
        "integrity",
        "error",
        "pre_existing",
    )
    assert "could not be checked" in errors[0].details and "boom" in errors[0].details
    assert any(r.ref.doc_key == stem(VIOLATING) and r.name == "brex" for r in found)


def test_empty_workspace():
    index, results = a1_indexer.run(wsmod.Workspace())
    assert index.docs == {} and results == []


# --- real Bike data (skipped when data/ is absent) ----------------------------


@pytest.mark.data41
def test_real_bike_41_baseline_is_fast_and_reports_counts(repo_root: Path):
    data = repo_root / "data" / "s1000d-4.1"
    source = wsmod.Source(
        id="bike41",
        path=(data / "bike").resolve(),
        brex_dirs=[(data / "brex").resolve()],
        issue="4.1",
        schemas_dir=(data / "schemas").resolve(),
    )
    start = time.perf_counter()
    index, results = a1_indexer.run(wsmod.Workspace([source], repo_root))
    elapsed = time.perf_counter() - start
    found = a1_indexer.problems(results)
    errors = sum(1 for r in found if r.severity == "error")
    dms = sum(1 for d in index.docs.values() if d.role == "dm")
    warnings = len(found) - errors
    print(f"Bike 4.1 baseline: {dms} DMs, {errors} errors, {warnings} warnings, {elapsed:.1f}s")
    assert dms > 0 and results
    assert {r.origin for r in results} == {"pre_existing"}
    assert elapsed < 10
