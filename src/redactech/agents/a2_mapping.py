"""A2 - request interpreter without AI: mapping tables and structured forms to operations.

``read_mapping`` reads a CSV (``;`` or ``,``, UTF-8) or XLSX table with the columns ``old``,
``new`` and optionally ``kind`` (default ``replace_part``) and ``reason``. ``from_mapping``
turns the rows into ``Operation`` objects whose ``source`` quotes the raw row, so every value
written later can be traced back to the request. ``from_form`` does the same for one structured
request (a dict). Nothing is guessed: a row or form with a missing value is refused.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from redactech.models import Operation, SourceSpan, Target

MAPPING_KINDS = ("replace_part", "replace_text")
RAW = "_raw"

# operation kind -> parameters that must be present (a tuple inside means "one of")
REQUIRED: dict[str, tuple[Any, ...]] = {
    "replace_part": ("old", "new"),
    "replace_text": ("old", "new"),
    "insert_step": ("para", ("after_id", "before_id")),
    "delete_step": ("step_id",),
    "move_step": ("step_id", ("after_id", "before_id")),
    "update_ref": (("dm_code", "internal_ref_id"),),
    "add_requirement": ("requirement", "part_number", "manufacturer_code", "quantity"),
    "remove_requirement": ("requirement", ("part_number", "id")),
}


class MappingError(ValueError):
    """A mapping row or a form cannot be turned into an operation (all problems are listed)."""


def _sniff_delimiter(first_line: str) -> str:
    return ";" if first_line.count(";") > first_line.count(",") else ","


def _read_csv(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = [line.rstrip("\r") for line in text.split("\n")]
    if not text.strip():
        return []
    delimiter = _sniff_delimiter(lines[0])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader, [])]
    previous = reader.line_num
    rows = []
    for values in reader:
        first, last = previous + 1, reader.line_num  # physical lines of this record
        previous = last
        cells = [v.strip() for v in values]
        if not any(cells):
            continue
        row = dict(zip(header, cells, strict=False))
        row[RAW] = "\n".join(lines[first - 1 : last]).strip()  # a quoted cell may span lines
        rows.append(row)
    return rows


def _read_xlsx(path: Path) -> list[dict[str, str]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        iterator = sheet.iter_rows(values_only=True)
        first = next(iterator, None)
        if first is None:
            return []
        header = ["" if c is None else str(c).strip().lower() for c in first]
        rows = []
        for values in iterator:
            cells = ["" if c is None else str(c).strip() for c in values]
            if not any(cells):
                continue
            row = dict(zip(header, cells, strict=False))
            row[RAW] = " | ".join(cells).strip()
            rows.append(row)
        return rows
    finally:
        workbook.close()


def read_mapping(path: Path | str) -> list[dict[str, str]]:
    """Rows of a mapping table (CSV or XLSX) as dicts with lower-case column names.

    Each row also has ``_raw``, the row as written in the file (used as the quote).
    """
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(file)
    if suffix in (".csv", ".txt", ""):
        return _read_csv(file)
    raise MappingError(f"unsupported mapping file type {file.suffix!r} (use .csv or .xlsx)")


def from_mapping(rows: list[dict[str, str]], doc: str = "mapping") -> list[Operation]:
    """One operation per row: ``kind`` (default replace_part), ``old``, ``new``, ``reason``."""
    operations: list[Operation] = []
    problems: list[str] = []
    for number, row in enumerate(rows, 1):
        kind = (row.get("kind") or "replace_part").strip()
        old, new = (row.get("old") or "").strip(), (row.get("new") or "").strip()
        if kind not in MAPPING_KINDS:
            problems.append(f"row {number}: kind {kind!r} is not allowed in a mapping")
            continue
        if not old or not new:
            problems.append(f"row {number}: both 'old' and 'new' are required")
            continue
        quote = row.get(RAW) or f"{old};{new}"
        operations.append(
            Operation(
                id=f"op-{number:04d}",
                kind=kind,
                target=Target(),
                params={"old": old, "new": new},
                rationale=(row.get("reason") or "").strip() or f"{old} replaced by {new}",
                source=[SourceSpan(doc=doc, quote=quote)],
            )
        )
    if problems:
        raise MappingError("; ".join(problems))
    return operations


def mapping_operations(path: Path | str) -> list[Operation]:
    """``read_mapping`` + ``from_mapping`` for a file."""
    file = Path(path)
    return from_mapping(read_mapping(file), doc=file.name)


def _missing(kind: str, params: dict[str, Any]) -> list[str]:
    missing = []
    for need in REQUIRED[kind]:
        names = need if isinstance(need, tuple) else (need,)
        if not any(params.get(n) not in (None, "") for n in names):
            missing.append(" or ".join(names))
    return missing


def from_form(form: dict[str, Any]) -> list[Operation]:
    """One operation from a structured request.

    ``form`` has ``kind``, ``params`` (or, for the replacements, ``old`` / ``new`` at the top
    level), an optional ``target`` (``ref``: {source_id, doc_key}, ``xpath``, ``element_id``) and
    an optional ``reason``. The source quote is the form itself.
    """
    kind = form.get("kind")
    if kind not in REQUIRED:
        raise MappingError(f"unknown or missing operation kind {kind!r}")
    params = dict(form.get("params") or {})
    for name in ("old", "new"):
        if name in form and name not in params:
            params[name] = form[name]
    missing = _missing(kind, params)
    if missing:
        raise MappingError(f"{kind}: missing parameter(s): {', '.join(missing)}")
    operation = Operation(
        id="op-0001",
        kind=kind,
        target=Target(**(form.get("target") or {})),
        params=params,
        rationale=str(form.get("reason") or "").strip() or f"{kind} requested by form",
        source=[SourceSpan(doc="form", quote=json.dumps(form, sort_keys=True, default=str))],
    )
    return [operation]
