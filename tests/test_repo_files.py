"""Repository hygiene: required files exist and the CI workflow is well formed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REQUIRED_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "QUALITY.md",
    "PLANNING.md",
    "CLAUDE.md",
    ".github/workflows/ci.yml",
    ".github/ISSUE_TEMPLATE/task.yml",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/pull_request_template.md",
]

QUALITY_IDS = ["REQ-3", *[f"REQ-{n}" for n in range(5, 12)]]
QUALITY_IDS += ["OBJ-1", "OBJ-10", "OBJ-19", "OBJ-21", "OBJ-22", "OBJ-23"]


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_required_file_exists(repo_root: Path, name: str):
    assert (repo_root / name).is_file(), name


def _ci(repo_root: Path) -> dict:
    return yaml.safe_load((repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


def test_ci_has_test_and_windows_jobs(repo_root: Path):
    jobs = _ci(repo_root)["jobs"]
    assert "test" in jobs and "windows" in jobs
    assert jobs["test"]["runs-on"] == "ubuntu-latest"
    assert jobs["windows"]["runs-on"] == "windows-latest"


def test_ci_windows_only_on_push_to_main(repo_root: Path):
    condition = _ci(repo_root)["jobs"]["windows"]["if"]
    assert "push" in condition and "refs/heads/main" in condition


def test_ci_runs_on_push_and_pull_request(repo_root: Path):
    triggers = _ci(repo_root).get("on", _ci(repo_root).get(True))  # YAML 1.1 parses `on` as True
    assert "push" in triggers and "pull_request" in triggers


def test_ci_commands(repo_root: Path):
    text = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ruff check ." in text
    assert 'not data41 and not data42 and not ollama' in text
    assert "tools/privacy.py scan --tracked" in text


@pytest.mark.parametrize("ident", QUALITY_IDS)
def test_quality_contains_id(repo_root: Path, ident: str):
    text = (repo_root / "QUALITY.md").read_text(encoding="utf-8")
    assert re.search(rf"\b{ident}\b", text), ident


def test_issue_templates_are_valid_yaml_forms(repo_root: Path):
    for name in ("task.yml", "bug.yml"):
        data = yaml.safe_load((repo_root / ".github/ISSUE_TEMPLATE" / name).read_text("utf-8"))
        assert data["name"] and data["body"]


def test_pyproject_points_to_readme(repo_root: Path):
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'readme = "README.md"' in text
