"""Files of the delivery: report.json / report.html, the questions export, decisions.jsonl.

* ``write_report(run_dir, report)``: ``report.json`` (the pydantic model) and ``report.html``.
* ``export_questions(state, path)``: the open questions as CSV (UTF-8 with a BOM so that
  spreadsheet tools detect the encoding, ``;`` separator) or XLSX, chosen by the extension.
  Columns: id, document, element, question/comment, status, rule.
* ``export_decisions(state, path)``: one JSON object per line, one line per decision taken.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from redactech.models import RunState
from redactech.report.build import QuestionEntry, Report, question_entries
from redactech.report.html import render_html

COLUMNS = ["id", "document", "element", "question/comment", "status", "rule"]


def write_report(run_dir: Path | str, report: Report) -> tuple[Path, Path]:
    """Write ``report.json`` and ``report.html`` into ``run_dir``; returns both paths."""
    folder = Path(run_dir)
    folder.mkdir(parents=True, exist_ok=True)
    json_path, html_path = folder / "report.json", folder / "report.html"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return json_path, html_path


def _row(entry: QuestionEntry) -> list[str]:
    return [entry.id, entry.document, entry.element, entry.text, entry.status, entry.rule]


def export_questions(state: RunState, path: Path | str) -> Path:
    """Write the open questions (``.csv`` or ``.xlsx``); returns the path."""
    target = Path(path)
    rows = [_row(entry) for entry in question_entries(state)]
    suffix = target.suffix.lower()
    target.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".csv":
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(COLUMNS)
            writer.writerows(rows)
    elif suffix == ".xlsx":
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "questions"
        sheet.append(COLUMNS)
        for row in rows:
            sheet.append(row)
        for cells in sheet.iter_rows():
            for cell in cells:  # a text starting with "=" is text, never a formula
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"
        workbook.save(target)
    else:
        raise ValueError(f"unsupported questions file type {target.suffix!r} (use .csv or .xlsx)")
    return target


def export_decisions(state: RunState, path: Path | str) -> Path:
    """Write the decisions of the run as JSON lines (UTF-8, one decision per line)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(entry, ensure_ascii=False, sort_keys=True)
        for entry in state.decisions_log
        if entry.get("event") == "decision"
    ]
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    return target
