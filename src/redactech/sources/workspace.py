"""Workspace: the S1000D sources the tool works on (``workspace.toml``).

File format (paths are relative to the folder of the workspace file)::

    [[sources]]
    id = "bike41"
    path = "data/s1000d-4.1/bike"
    brex_dirs = ["data/s1000d-4.1/brex"]
    issue = "4.1"
    writable = true
    schemas_dir = "data/s1000d-4.1/schemas"   # optional

``schemas_dir`` defaults to the ``schemas`` folder next to the source folder (for instance
``data/s1000d-4.1/schemas`` for ``data/s1000d-4.1/bike``) when it exists.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from redactech.models import SourceDoc
from redactech.sources.classify import classify

EXAMPLE_NAME = "workspace.example.toml"
EXAMPLE_TOML = """\
# Copy to workspace.toml (ignored by git), then adapt the paths.

[[sources]]
id = "bike41"
path = "data/s1000d-4.1/bike"
brex_dirs = ["data/s1000d-4.1/brex"]
issue = "4.1"
writable = true

[[sources]]
id = "bike42"
path = "data/s1000d-4.2/bike"
brex_dirs = ["data/s1000d-4.2/brex"]
issue = "4.2"
writable = true

[[sources]]
id = "fixtures"
path = "tests/fixtures/s1000d"
brex_dirs = ["tests/fixtures/s1000d"]
issue = "4.1"
writable = true
"""


@dataclass
class Source:
    id: str
    path: Path
    brex_dirs: list[Path] = field(default_factory=list)
    issue: str | None = None
    writable: bool = True
    schemas_dir: Path | None = None


@dataclass
class Workspace:
    sources: list[Source] = field(default_factory=list)
    root: Path = field(default_factory=Path.cwd)

    def source(self, source_id: str) -> Source:
        for src in self.sources:
            if src.id == source_id:
                return src
        raise KeyError(source_id)


def _default_schemas_dir(path: Path) -> Path | None:
    candidate = path.parent / "schemas"
    return candidate if candidate.is_dir() else None


def _resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p).resolve()


def load_workspace(path: Path | str) -> Workspace:
    """Read a workspace file. Raises ``ValueError`` for a malformed source entry."""
    file = Path(path)
    root = file.resolve().parent
    with file.open("rb") as fh:
        data = tomllib.load(fh)
    sources: list[Source] = []
    seen: set[str] = set()
    for number, entry in enumerate(data.get("sources", []), 1):
        source_id = entry.get("id")
        raw_path = entry.get("path")
        if not source_id or not raw_path:
            raise ValueError(f"source #{number} needs an 'id' and a 'path'")
        if source_id in seen:
            raise ValueError(f"duplicate source id {source_id!r}")
        seen.add(source_id)
        src_path = _resolve(root, raw_path)
        schemas = entry.get("schemas_dir")
        sources.append(
            Source(
                id=source_id,
                path=src_path,
                brex_dirs=[_resolve(root, d) for d in entry.get("brex_dirs", [])],
                issue=entry.get("issue"),
                writable=bool(entry.get("writable", True)),
                schemas_dir=_resolve(root, schemas) if schemas else _default_schemas_dir(src_path),
            )
        )
    return Workspace(sources=sources, root=root)


def _example_text() -> str:
    # <repo>/src/redactech/sources/workspace.py -> <repo>/workspace.example.toml
    candidate = Path(__file__).resolve().parents[3] / EXAMPLE_NAME
    return candidate.read_text(encoding="utf-8") if candidate.is_file() else EXAMPLE_TOML


def init_workspace(path: Path | str, force: bool = False) -> Path:
    """Create a workspace file from ``workspace.example.toml`` (or the embedded copy)."""
    target = Path(path)
    if target.exists() and not force:
        raise FileExistsError(str(target))
    target.write_text(_example_text(), encoding="utf-8", newline="\n")
    return target


def _slug(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-")
    return cleaned.lower() or "source"


def _issue_from_path(path: Path) -> str | None:
    for part in reversed(path.parts):
        low = part.lower()
        for issue in ("4.1", "4.2"):
            if low == f"s1000d-{issue}":
                return issue
    return None


def add_source(
    ws: Workspace,
    path: Path | str,
    id: str | None = None,  # noqa: A002 - mirrors the TOML key
    brex_dirs: tuple[Path | str, ...] | list[Path | str] = (),
) -> Source:
    """Add a source folder. Without ``brex_dirs``, a sibling ``brex`` folder is used if present."""
    src_path = Path(path).resolve()
    if not src_path.is_dir():
        raise NotADirectoryError(str(src_path))
    taken = {s.id for s in ws.sources}
    if id is not None and id in taken:
        raise ValueError(f"duplicate source id {id!r}")
    base = id or _slug(src_path.name)
    source_id, n = base, 1
    while source_id in taken:
        n += 1
        source_id = f"{base}-{n}"
    dirs = [Path(d).resolve() for d in brex_dirs]
    if not dirs and (src_path.parent / "brex").is_dir():
        dirs = [(src_path.parent / "brex").resolve()]
    source = Source(
        id=source_id,
        path=src_path,
        brex_dirs=dirs,
        issue=_issue_from_path(src_path.parent) or _issue_from_path(src_path),
        writable=True,
        schemas_dir=_default_schemas_dir(src_path),
    )
    ws.sources.append(source)
    return source


def _rel(root: Path, target: Path) -> str:
    try:
        return Path(os.path.relpath(target, root)).as_posix()
    except ValueError:  # other drive on Windows
        return target.as_posix()


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def save_workspace(ws: Workspace, path: Path | str) -> Path:
    """Write the workspace; paths are stored relative to the file when possible."""
    file = Path(path)
    root = file.resolve().parent
    lines = ["# RedacTech workspace: sources and their BREX folders.", ""]
    for src in ws.sources:
        lines.append("[[sources]]")
        lines.append(f"id = {_q(src.id)}")
        lines.append(f"path = {_q(_rel(root, src.path))}")
        dirs = ", ".join(_q(_rel(root, d)) for d in src.brex_dirs)
        lines.append(f"brex_dirs = [{dirs}]")
        if src.issue:
            lines.append(f"issue = {_q(src.issue)}")
        lines.append(f"writable = {'true' if src.writable else 'false'}")
        if src.schemas_dir is not None:
            lines.append(f"schemas_dir = {_q(_rel(root, src.schemas_dir))}")
        lines.append("")
    file.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return file


def scan(ws: Workspace) -> list[SourceDoc]:
    """Classify every file of every source folder and of its BREX folders.

    Folders are read flat (no recursion). BREX data modules found in a ``brex_dirs`` folder are
    role ``brex``; other files of a BREX folder are ignored. A file that appears twice for one
    source (same ``doc_key``) is listed once, the source folder winning. ``issue`` falls back to
    the source's; ``writable`` is forced to False when the source is read-only.
    """
    docs: list[SourceDoc] = []
    for src in ws.sources:
        seen: set[str] = set()
        folders = [(src.path, False), *[(d, True) for d in src.brex_dirs]]
        done: set[Path] = set()
        for folder, brex_only in folders:
            if folder in done or not folder.is_dir():
                continue
            done.add(folder)
            for file in sorted(p for p in folder.iterdir() if p.is_file()):
                doc = classify(file, source_id=src.id)
                if brex_only and doc.role != "brex":
                    continue
                if doc.ref.doc_key in seen:
                    continue
                seen.add(doc.ref.doc_key)
                update: dict[str, object] = {}
                if doc.issue is None and src.issue and doc.kind == "s1000d":
                    update["issue"] = src.issue
                if not src.writable:
                    update["writable"] = False
                docs.append(doc.model_copy(update=update) if update else doc)
    return docs
