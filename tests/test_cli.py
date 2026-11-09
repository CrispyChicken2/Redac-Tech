"""Tests of the CLI skeleton."""

from __future__ import annotations

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
        ["workspace", "init"],
        ["workspace", "add", "some/path"],
        ["workspace", "list"],
        ["index"],
        ["baseline"],
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
