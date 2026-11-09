"""Tests of redactech.agents.a2_mapping (mapping tables and forms to operations)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redactech.agents import a2_mapping as a2
from redactech.models import Operation


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- reading ------------------------------------------------------------------


def test_csv_with_semicolons(tmp_path: Path):
    path = write(tmp_path, "m.csv", "old;new;reason\nLRU1010;LRU2020;obsolete\nX2;X3;\n")
    rows = a2.read_mapping(path)
    assert [(r["old"], r["new"], r["reason"]) for r in rows] == [
        ("LRU1010", "LRU2020", "obsolete"),
        ("X2", "X3", ""),
    ]
    assert rows[0][a2.RAW] == "LRU1010;LRU2020;obsolete"


def test_csv_with_commas_bom_blank_lines_and_mixed_case_header(tmp_path: Path):
    bom = chr(0xFEFF)  # a UTF-8 byte order mark, as written by spreadsheet exports
    text = bom + "Old, New ,Kind,Reason\n"
    text += 'LRU1010,LRU2020,replace_part,"part, replaced"\n\n,,,\nX2,X3,,\n'
    rows = a2.read_mapping(write(tmp_path, "m.csv", text))
    assert len(rows) == 2
    assert rows[0]["old"] == "LRU1010" and rows[0]["new"] == "LRU2020"
    assert rows[0]["reason"] == "part, replaced"
    assert rows[1]["old"] == "X2" and rows[1]["kind"] == ""


def test_csv_cell_spanning_several_lines_keeps_rows_and_quotes_aligned(tmp_path: Path):
    text = 'old;new;reason\nA;B;"line one\nline two"\nC;D;ok\n'
    rows = a2.read_mapping(write(tmp_path, "m.csv", text))
    assert [(r["old"], r["new"]) for r in rows] == [("A", "B"), ("C", "D")]
    assert rows[0]["reason"] == "line one\nline two"
    assert rows[0][a2.RAW] == 'A;B;"line one\nline two"'
    assert rows[1][a2.RAW] == "C;D;ok"


def test_csv_with_windows_line_endings(tmp_path: Path):
    path = tmp_path / "m.csv"
    path.write_bytes(b"old;new\r\nA;B\r\n\r\nC;D\r\n")
    rows = a2.read_mapping(path)
    assert [(r["old"], r["new"], r[a2.RAW]) for r in rows] == [
        ("A", "B", "A;B"),
        ("C", "D", "C;D"),
    ]


def test_empty_csv(tmp_path: Path):
    assert a2.read_mapping(write(tmp_path, "m.csv", "")) == []
    assert a2.read_mapping(write(tmp_path, "h.csv", "old;new\n")) == []


def test_xlsx_generated_at_test_time(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Old", "New", "Kind", "Reason"])
    sheet.append(["LRU1010", "LRU2020", None, "obsolete"])
    sheet.append([None, None, None, None])
    sheet.append([1234, 5678, "replace_text", None])
    path = tmp_path / "m.xlsx"
    workbook.save(path)
    rows = a2.read_mapping(path)
    assert len(rows) == 2
    assert (rows[0]["old"], rows[0]["new"], rows[0]["kind"], rows[0]["reason"]) == (
        "LRU1010",
        "LRU2020",
        "",
        "obsolete",
    )
    assert (rows[1]["old"], rows[1]["new"], rows[1]["kind"]) == ("1234", "5678", "replace_text")
    assert rows[0][a2.RAW] == "LRU1010 | LRU2020 |  | obsolete"


def test_unsupported_file_type(tmp_path: Path):
    with pytest.raises(a2.MappingError):
        a2.read_mapping(write(tmp_path, "m.pdf", "x"))


# --- from_mapping -------------------------------------------------------------


def test_operations_from_rows(tmp_path: Path):
    text = "old;new;kind;reason\nLRU1010;LRU2020;;obsolete\nfoo;bar;replace_text;typo\n"
    path = write(tmp_path, "lots.csv", text)
    operations = a2.mapping_operations(path)
    assert all(isinstance(o, Operation) for o in operations)
    first, second = operations
    assert (first.id, first.kind, first.params) == (
        "op-0001",
        "replace_part",
        {"old": "LRU1010", "new": "LRU2020"},
    )
    assert first.rationale == "obsolete" and first.confidence == 1.0
    assert first.target.ref is None and first.questions == []
    assert (second.id, second.kind, second.rationale) == ("op-0002", "replace_text", "typo")
    (span,) = first.source
    assert span.doc == "lots.csv" and span.quote == "LRU1010;LRU2020;;obsolete"


def test_default_rationale_and_values_are_stripped():
    rows = [{"old": " LRU1010 ", "new": " LRU2020", "_raw": "raw"}]
    (op,) = a2.from_mapping(rows, doc="x.csv")
    assert op.params == {"old": "LRU1010", "new": "LRU2020"}
    assert op.rationale == "LRU1010 replaced by LRU2020"
    assert op.source[0].quote == "raw"


def test_every_problem_is_reported_at_once():
    rows = [
        {"old": "A", "new": ""},
        {"old": "B", "new": "C", "kind": "insert_step"},
        {"old": "D", "new": "E"},
    ]
    with pytest.raises(a2.MappingError) as error:
        a2.from_mapping(rows)
    assert "row 1" in str(error.value) and "row 2" in str(error.value)
    assert "row 3" not in str(error.value)


# --- from_form ----------------------------------------------------------------


def test_form_replace_shorthand():
    form = {"kind": "replace_part", "old": "LRU1010", "new": "LRU2020", "reason": "r"}
    (op,) = a2.from_form(form)
    assert (op.kind, op.params, op.rationale) == (
        "replace_part",
        {"old": "LRU1010", "new": "LRU2020"},
        "r",
    )
    assert op.source[0].doc == "form"
    assert json.loads(op.source[0].quote)["old"] == "LRU1010"


def test_form_with_params_and_target():
    form = {
        "kind": "insert_step",
        "params": {"after_id": "stp-0002", "para": "Check."},
        "target": {"ref": {"source_id": "s", "doc_key": "d"}, "element_id": "stp-0002"},
    }
    (op,) = a2.from_form(form)
    assert op.target.ref.doc_key == "d" and op.target.element_id == "stp-0002"
    assert op.params["para"] == "Check." and op.rationale


@pytest.mark.parametrize(
    "form",
    [
        {},
        {"kind": "translate_dm"},
        {"kind": "replace_part", "old": "A"},
        {"kind": "insert_step", "params": {"para": "x"}},
        {"kind": "move_step", "params": {"step_id": "a"}},
        {"kind": "update_ref", "params": {}},
        {"kind": "add_requirement", "params": {"requirement": "spare", "part_number": "P"}},
        {"kind": "remove_requirement", "params": {"requirement": "spare"}},
        {"kind": "delete_step", "params": {}},
    ],
)
def test_form_refuses_incomplete_requests(form: dict):
    with pytest.raises(a2.MappingError):
        a2.from_form(form)


@pytest.mark.parametrize(
    "form",
    [
        {"kind": "delete_step", "params": {"step_id": "stp-0001"}},
        {"kind": "move_step", "params": {"step_id": "a", "before_id": "b"}},
        {"kind": "update_ref", "params": {"internal_ref_id": "x"}},
        {"kind": "update_ref", "params": {"dm_code": {"infoCode": "520"}}},
        {
            "kind": "add_requirement",
            "params": {
                "requirement": "spare",
                "part_number": "P",
                "manufacturer_code": "M",
                "quantity": 1,
            },
        },
        {"kind": "remove_requirement", "params": {"requirement": "spare", "id": "spr-0001"}},
        {"kind": "replace_text", "old": "a", "new": "b"},
    ],
)
def test_form_accepts_complete_requests(form: dict):
    (op,) = a2.from_form(form)
    assert op.kind == form["kind"]
