"""Tests of redactech.report.export: report files, questions (CSV / XLSX), decisions."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from redactech.report import build, export

HEADER = ["id", "document", "element", "question/comment", "status", "rule"]


def rows_of_csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter=";"))


# --- report.json and report.html ------------------------------------------------------------


def test_write_report_makes_the_json_and_the_html(tmp_path: Path, state, index, write_result):
    report = build.build_report(state, index, write_result)
    json_path, html_path = export.write_report(tmp_path / "run", report)
    assert (json_path.name, html_path.name) == ("report.json", "report.html")
    assert build.Report.model_validate_json(json_path.read_text(encoding="utf-8")) == report
    assert html_path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert "20250307-140509-ab12" in json.loads(json_path.read_text(encoding="utf-8"))["run_id"]


# --- questions -------------------------------------------------------------------------------


def test_the_csv_has_a_bom_the_semicolon_and_the_columns(tmp_path: Path, state, consts):
    path = export.export_questions(state, tmp_path / "questions.csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b";" in raw.splitlines()[0]
    assert raw.splitlines()[0].decode("utf-8-sig") == ";".join(HEADER)
    rows = rows_of_csv(path)
    assert rows[0] == HEADER
    comment = "Ask the customer <b>?</b>"
    assert rows[1] == ["p2", consts.key_b, "el-z2", comment, "pending_client", ""]
    assert rows[2] == ["p4", consts.key_a, "el-z4", consts.question, "blocked_by_rule",
                       "R-1: No <note> here."]
    assert rows[3] == ["op-0003", consts.key_b, "el-3", "Is the wording right?", "open", ""]


def test_a_cell_with_the_separator_quotes_or_newlines_survives(tmp_path: Path, state):
    tricky = 'a; "b"\nc'
    state.proposals[1] = state.proposals[1].model_copy(update={"reviewer_comment": tricky})
    rows = rows_of_csv(export.export_questions(state, tmp_path / "q.csv"))
    assert rows[1][3] == tricky


def test_the_xlsx_reads_back_with_the_same_rows(tmp_path: Path, state, consts):
    path = export.export_questions(state, tmp_path / "questions.xlsx")
    sheet = load_workbook(path).active
    values = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
    assert values[0] == HEADER
    assert [row[0] for row in values[1:]] == ["p2", "p4", "op-0003"]
    assert values[2][3] == consts.question and values[2][5] == "R-1: No <note> here."


@pytest.mark.parametrize("start", ["=", "+", "-", "@"])
@pytest.mark.parametrize("extension", [".csv", ".xlsx"])
def test_a_text_that_looks_like_a_formula_gets_an_apostrophe(
    tmp_path: Path, state, start: str, extension: str
):
    text = f"{start}1+1"
    state.proposals[1] = state.proposals[1].model_copy(update={"reviewer_comment": text})
    path = export.export_questions(state, tmp_path / f"q{extension}")
    if extension == ".csv":
        value = rows_of_csv(path)[1][3]
    else:
        value = load_workbook(path).active["D2"].value
    assert value == "'" + text


def test_ordinary_texts_are_left_alone(tmp_path: Path, state):
    assert export.safe_cell("R-1: rule") == "R-1: rule" and export.safe_cell("") == ""
    rows = rows_of_csv(export.export_questions(state, tmp_path / "q.csv"))
    assert rows[2][0] == "p4" and rows[3][0] == "op-0003"  # an id with a hyphen inside is fine


def test_no_question_gives_only_the_header(tmp_path: Path, state):
    state.proposals, state.operations = [], []
    assert rows_of_csv(export.export_questions(state, tmp_path / "q.csv")) == [HEADER]


def test_an_unknown_extension_is_refused(tmp_path: Path, state):
    with pytest.raises(ValueError, match="csv or .xlsx"):
        export.export_questions(state, tmp_path / "questions.txt")
    assert not (tmp_path / "questions.txt").exists()


def test_parent_folders_are_created(tmp_path: Path, state):
    path = export.export_questions(state, tmp_path / "a" / "b" / "q.csv")
    assert path.is_file()


# --- decisions -------------------------------------------------------------------------------


def test_decisions_are_one_json_object_per_line(tmp_path: Path, state):
    path = export.export_decisions(state, tmp_path / "decisions.jsonl")
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and "\r" not in text
    lines = text.splitlines()
    assert len(lines) == 2  # the two decisions, not the other events
    first, second = (json.loads(line) for line in lines)
    assert (first["proposal"], first["status"], first["actor"]) == ("p1", "accepted", "user")
    assert second["comment"] == "Ask the customer <b>?</b>"
    assert all(entry["event"] == "decision" and entry["time"] for entry in (first, second))


def test_no_decision_gives_an_empty_file(tmp_path: Path, state):
    state.decisions_log = [{"event": "ops_proposed", "time": "t"}]
    path = export.export_decisions(state, tmp_path / "decisions.jsonl")
    assert path.read_text(encoding="utf-8") == ""
