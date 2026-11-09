"""Privacy and hygiene audit of the real repository (uses the local denylist if present)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import privacy  # noqa: E402


def _git(*args: str) -> str:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return res.stdout


def _tracked() -> list[str]:
    return [p for p in _git("ls-files", "-z").split("\0") if p]


def test_no_denylist_term_in_tracked_files():
    terms = privacy.load_denylist(REPO)
    if terms is None:
        pytest.skip("no local denylist available")
    allow = privacy.load_allowlist(REPO)
    hits = privacy.scan_tracked(REPO, terms, allow)
    assert not hits, "\n".join(str(h) for h in hits)  # excerpts are masked


FORBIDDEN_PREFIXES = ("runs/", ".agents/", ".worktrees/", ".cache/", ".handoff/", "tasks/")


def test_no_forbidden_path_tracked():
    for path in _tracked():
        assert not path.startswith(FORBIDDEN_PREFIXES), path
        if path.startswith("data/"):
            assert path == "data/README.md", path
        assert not path.lower().endswith(".zip"), path


def test_agents_dir_is_ignored():
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".agents/" in [line.strip() for line in gitignore]
    common = Path(_git("rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = REPO / common
    exclude = (common / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert any(line.strip().strip("/") == ".agents" for line in exclude)
