"""Tests of the CLI: implemented commands and remaining stubs."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from redactech.cli import app

runner = CliRunner()

COMMANDS = [
    "workspace", "index", "baseline", "request", "review", "write", "check", "render", "eval",
]


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in COMMANDS:
        assert name in result.output


def test_workspace_help_lists_subcommands():
    result = runner.invoke(app, ["workspace", "--help"])
    assert result.exit_code == 0
    for name in ("init", "add", "list"):
        assert name in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["request", "--mapping", "lots.xlsx", "--version-policy", "in_work", "--out", "runs/"],
        ["review", "runs/x"],
        ["write", "runs/x"],
        ["check", "runs/x/out"],
        ["render", "doc.xml", "--view", "xml", "--show-deleted"],
        ["eval", "tests/scenarios/"],
    ],
    ids=lambda a: " ".join(a),
)
def test_stub_exits_2(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "not implemented yet" in result.output


# --- workspace init / add / list, index, baseline -----------------------------


def run(*args: str):
    return runner.invoke(app, list(args))


@pytest.fixture
def ws_file(tmp_path: Path) -> Path:
    return tmp_path / "ws.toml"


def test_workspace_init_creates_and_refuses_to_overwrite(ws_file: Path):
    result = run("workspace", "init", "--workspace", str(ws_file))
    assert result.exit_code == 0 and "created" in result.output
    assert "bike41" in ws_file.read_text(encoding="utf-8")
    again = run("workspace", "init", "-w", str(ws_file))
    assert again.exit_code == 1 and "already exists" in again.output
    forced = run("workspace", "init", "-w", str(ws_file), "--force")
    assert forced.exit_code == 0


def test_workspace_commands_need_a_workspace_file(ws_file: Path):
    for args in (["workspace", "list"], ["workspace", "add", str(ws_file.parent)], ["index"]):
        result = run(*args, "-w", str(ws_file))
        assert result.exit_code == 1 and "workspace init" in result.output


def test_workspace_add_and_list(ws_file: Path, tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "bx").mkdir()
    ws_file.write_text("# empty\n", encoding="utf-8")
    listing = run("workspace", "list", "-w", str(ws_file))
    assert listing.exit_code == 0 and "no sources" in listing.output
    added = run(
        "workspace", "add", str(tmp_path / "src"), "--id", "mine",
        "--brex-dir", str(tmp_path / "bx"), "-w", str(ws_file),
    )
    assert added.exit_code == 0 and "added mine" in added.output
    listing = run("workspace", "list", "-w", str(ws_file))
    assert listing.exit_code == 0
    assert "mine" in listing.output and "writable" in listing.output and "brex:" in listing.output
    duplicate = run("workspace", "add", str(tmp_path / "src"), "--id", "mine", "-w", str(ws_file))
    assert duplicate.exit_code == 1 and "cannot add source" in duplicate.output
    missing = run("workspace", "add", str(tmp_path / "nope"), "-w", str(ws_file))
    assert missing.exit_code == 1


def test_invalid_workspace_file_is_reported(ws_file: Path):
    ws_file.write_text('[[sources]]\npath = "p"\n', encoding="utf-8")
    result = run("workspace", "list", "-w", str(ws_file))
    assert result.exit_code == 1 and "invalid workspace" in result.output


@pytest.fixture
def fixtures_ws(ws_file: Path, repo_root: Path) -> Path:
    folder = repo_root / "tests" / "fixtures" / "s1000d"
    ws_file.write_text("# fixtures\n", encoding="utf-8")
    result = run(
        "workspace", "add", str(folder), "--id", "fixtures", "--brex-dir", str(folder),
        "-w", str(ws_file),
    )
    assert result.exit_code == 0
    return ws_file


def test_index_prints_counts_per_source_and_role(fixtures_ws: Path):
    result = run("index", "-w", str(fixtures_ws))
    assert result.exit_code == 0
    assert "fixtures: 12 files (brex=2, dm=9, upf=1)" in result.output
    assert "total: 12 files" in result.output


def test_baseline_prints_pre_existing_problems_per_data_module(fixtures_ws: Path):
    result = run("baseline", "-w", str(fixtures_ws))
    assert result.exit_code == 0
    assert "-521A-A_001-00_EN-US: 1 error(s), 0 warning(s) pre-existing" in result.output
    assert "-520A-A_001-00_EN-US: 0 error(s), 0 warning(s) pre-existing" in result.output
    assert "baseline: 9 data modules, 1 error(s), 0 warning(s) pre-existing" in result.output
    assert "no schemas folder for source(s) fixtures" in result.output
    assert "fixtures:DMC-RTPROTO-" in result.output  # lines are keyed by source and document


def test_default_workspace_file_comes_from_the_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    created = run("workspace", "init")
    assert created.exit_code == 0 and (tmp_path / "workspace.toml").is_file()
