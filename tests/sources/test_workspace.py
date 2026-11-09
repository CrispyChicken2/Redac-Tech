"""Tests of redactech.sources.workspace."""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

import pytest

from redactech.sources import workspace as wsmod

PROCED = "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML"
PROJECT = "DMC-RTPROTO-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"
DEFAULT = "DMC-RTDEFLT-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"


def make_tree(root: Path) -> Path:
    """data/a (+ data/schemas), data/brex, other, and a workspace file next to them."""
    for name in ("data/a", "data/brex", "data/schemas", "other"):
        (root / name).mkdir(parents=True, exist_ok=True)
    file = root / "workspace.toml"
    file.write_text(
        """
[[sources]]
id = "a"
path = "data/a"
brex_dirs = ["data/brex"]
issue = "4.1"
writable = false

[[sources]]
id = "b"
path = "other"
""",
        encoding="utf-8",
    )
    return file


def fixture_source(fixtures_dir: Path, **overrides) -> wsmod.Source:
    folder = fixtures_dir.resolve()
    values = {"id": "fixtures", "path": folder, "brex_dirs": [folder], "issue": "4.1"}
    return wsmod.Source(**{**values, **overrides})


# --- load ---------------------------------------------------------------------


def test_load_resolves_paths_against_the_workspace_file(tmp_path: Path):
    ws = wsmod.load_workspace(make_tree(tmp_path))
    a, b = ws.sources
    assert ws.root == tmp_path.resolve()
    assert a.id == "a" and a.path == (tmp_path / "data" / "a").resolve()
    assert a.brex_dirs == [(tmp_path / "data" / "brex").resolve()]
    assert (a.issue, a.writable) == ("4.1", False)
    assert a.schemas_dir == (tmp_path / "data" / "schemas").resolve()  # sibling default
    assert (b.issue, b.writable, b.brex_dirs, b.schemas_dir) == (None, True, [], None)
    assert ws.source("b") is b
    with pytest.raises(KeyError):
        ws.source("nope")


def test_explicit_schemas_dir(tmp_path: Path):
    (tmp_path / "s").mkdir()
    file = tmp_path / "workspace.toml"
    file.write_text(
        '[[sources]]\nid = "x"\npath = "s"\nschemas_dir = "elsewhere"\n', encoding="utf-8"
    )
    assert wsmod.load_workspace(file).sources[0].schemas_dir == (tmp_path / "elsewhere").resolve()


@pytest.mark.parametrize(
    "text",
    [
        '[[sources]]\npath = "p"\n',
        '[[sources]]\nid = "x"\n',
        '[[sources]]\nid = "x"\npath = "p"\n[[sources]]\nid = "x"\npath = "q"\n',
    ],
    ids=["no-id", "no-path", "duplicate-id"],
)
def test_malformed_sources_are_refused(tmp_path: Path, text: str):
    file = tmp_path / "workspace.toml"
    file.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        wsmod.load_workspace(file)


def test_file_without_sources_is_an_empty_workspace(tmp_path: Path):
    file = tmp_path / "workspace.toml"
    file.write_text("# nothing\n", encoding="utf-8")
    assert wsmod.load_workspace(file).sources == []


# --- init ---------------------------------------------------------------------


def test_init_copies_the_example(tmp_path: Path, repo_root: Path):
    target = tmp_path / "workspace.toml"
    assert wsmod.init_workspace(target) == target
    example = (repo_root / "workspace.example.toml").read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == example
    assert [s.id for s in wsmod.load_workspace(target).sources] == ["bike41", "bike42", "fixtures"]


def test_init_does_not_overwrite_unless_forced(tmp_path: Path):
    target = tmp_path / "workspace.toml"
    target.write_text("mine", encoding="utf-8")
    with pytest.raises(FileExistsError):
        wsmod.init_workspace(target)
    assert target.read_text(encoding="utf-8") == "mine"
    wsmod.init_workspace(target, force=True)
    assert "bike41" in target.read_text(encoding="utf-8")


def test_embedded_example_matches_the_file(repo_root: Path):
    example = (repo_root / "workspace.example.toml").read_text(encoding="utf-8")
    assert wsmod.EXAMPLE_TOML == example


# --- add / save ---------------------------------------------------------------


def test_add_source_defaults(tmp_path: Path):
    for name in ("s1000d-4.1/bike", "s1000d-4.1/brex", "s1000d-4.1/schemas"):
        (tmp_path / name).mkdir(parents=True)
    ws = wsmod.Workspace(root=tmp_path)
    src = wsmod.add_source(ws, tmp_path / "s1000d-4.1" / "bike")
    assert src.id == "bike" and src.issue == "4.1" and src.writable
    assert src.brex_dirs == [(tmp_path / "s1000d-4.1" / "brex").resolve()]
    assert src.schemas_dir == (tmp_path / "s1000d-4.1" / "schemas").resolve()
    again = wsmod.add_source(ws, tmp_path / "s1000d-4.1" / "bike")
    assert again.id == "bike-2" and [s.id for s in ws.sources] == ["bike", "bike-2"]


def test_add_source_explicit_values_and_errors(tmp_path: Path):
    (tmp_path / "one").mkdir()
    (tmp_path / "bx").mkdir()
    ws = wsmod.Workspace(root=tmp_path)
    src = wsmod.add_source(ws, tmp_path / "one", id="custom", brex_dirs=[tmp_path / "bx"])
    assert (src.id, src.brex_dirs, src.issue) == ("custom", [(tmp_path / "bx").resolve()], None)
    with pytest.raises(ValueError):
        wsmod.add_source(ws, tmp_path / "one", id="custom")
    with pytest.raises(NotADirectoryError):
        wsmod.add_source(ws, tmp_path / "missing")


def test_save_and_load_round_trip_with_relative_paths(tmp_path: Path):
    file = make_tree(tmp_path)
    ws = wsmod.load_workspace(file)
    wsmod.add_source(ws, tmp_path / "other", id="third")
    out = tmp_path / "saved.toml"
    wsmod.save_workspace(ws, out)
    text = out.read_text(encoding="utf-8")
    assert 'path = "data/a"' in text and 'brex_dirs = ["data/brex"]' in text
    assert "writable = false" in text
    again = wsmod.load_workspace(out)
    assert again.sources == ws.sources


def test_round_trip_with_non_ascii_folder_names(tmp_path: Path):
    folder = tmp_path / "données 'x'"
    folder.mkdir()
    ws = wsmod.Workspace(root=tmp_path)
    wsmod.add_source(ws, folder, id="é")
    out = tmp_path / "workspace.toml"
    wsmod.save_workspace(ws, out)
    again = wsmod.load_workspace(out)
    assert again.sources[0].id == "é" and again.sources[0].path == folder.resolve()


# --- scan ---------------------------------------------------------------------


def test_scan_fixtures_roles(fixtures_dir: Path):
    docs = wsmod.scan(wsmod.Workspace([fixture_source(fixtures_dir)], fixtures_dir))
    assert len(docs) == 12  # BREX folder == source folder: no duplicates, security/ not scanned
    assert Counter(d.role for d in docs) == {"dm": 9, "brex": 2, "upf": 1}
    assert {d.ref.source_id for d in docs} == {"fixtures"}
    assert len({d.ref.doc_key for d in docs}) == 12
    assert {d.issue for d in docs} == {"4.1"}
    assert {d.writable for d in docs if d.role == "dm"} == {True}
    assert {d.writable for d in docs if d.role in ("brex", "upf")} == {False}


def test_read_only_source_makes_everything_read_only(fixtures_dir: Path):
    ws = wsmod.Workspace([fixture_source(fixtures_dir, writable=False)], fixtures_dir)
    assert {d.writable for d in wsmod.scan(ws)} == {False}


def test_brex_folder_adds_only_brex_and_source_wins_on_duplicates(
    tmp_path: Path, fixtures_dir: Path
):
    src, bx = tmp_path / "src", tmp_path / "brex"
    src.mkdir()
    bx.mkdir()
    shutil.copy(fixtures_dir / PROCED, src / PROCED)
    shutil.copy(fixtures_dir / PROJECT, src / PROJECT)  # also present in the BREX folder
    shutil.copy(fixtures_dir / PROJECT, bx / PROJECT)
    shutil.copy(fixtures_dir / DEFAULT, bx / DEFAULT)
    shutil.copy(fixtures_dir / PROCED, bx / PROCED)  # a DM in a BREX folder: ignored
    ws = wsmod.Workspace(
        [wsmod.Source("s", src.resolve(), [bx.resolve()], "4.1")], tmp_path
    )
    docs = {d.ref.doc_key: d for d in wsmod.scan(ws)}
    assert len(docs) == 3
    assert Path(docs[PROJECT.removesuffix(".XML")].path).parent == src.resolve()
    assert Path(docs[DEFAULT.removesuffix(".XML")].path).parent == bx.resolve()
    assert Counter(d.role for d in docs.values()) == {"dm": 1, "brex": 2}


def test_scan_is_flat_and_tolerates_missing_folders(tmp_path: Path):
    (tmp_path / "src" / "nested").mkdir(parents=True)
    (tmp_path / "src" / "nested" / "DMC-A-B_001-00_EN-US.XML").write_bytes(b"<dmodule/>")
    (tmp_path / "src" / "notes.txt").write_bytes(b"x")
    ws = wsmod.Workspace(
        [wsmod.Source("s", (tmp_path / "src").resolve(), [tmp_path / "missing"])], tmp_path
    )
    docs = wsmod.scan(ws)
    assert [d.ref.doc_key for d in docs] == ["notes"] and docs[0].role == "other"


def test_issue_falls_back_to_the_source_issue(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "DMC-A-B_001-00_EN-US.XML").write_bytes(b"<dmodule/>")
    ws = wsmod.Workspace([wsmod.Source("s", (tmp_path / "src").resolve(), [], "4.2")], tmp_path)
    (doc,) = wsmod.scan(ws)
    assert (doc.role, doc.issue) == ("dm", "4.2")
