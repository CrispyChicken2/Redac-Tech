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


# --- README and roadmap (REQ-9, M2 exit) -----------------------------------------------------

INSTALL_COMMANDS = [
    'pip install -e ".[dev]"',
    "py -3 tools/setup_data.py",
    "streamlit run src/redactech/ui/app.py",
]
ROADMAP_ITEMS = [
    "Compare mode", "three-way merge", "Cross-document contradictions", "Non-XML inputs",
    "Generic-XML profiles", "Guided mode", "Step writing with RAG", "Translation",
    "STE checks", "CGM to SVG", "illustration consistency", "Issue alias tables",
    "Embeddings and RAG", "ROI", "Property-based tests", "Windows CI matrix",
]
KNOWN_GAPS = ["real data sets", "Grouped checks in A7", "Figure flags per IPD figure number"]


def _readme(repo_root: Path) -> str:
    return (repo_root / "README.md").read_text(encoding="utf-8")


def test_readme_gives_the_install_and_run_commands(repo_root: Path):
    text = _readme(repo_root)
    for command in INSTALL_COMMANDS:
        assert command in text, command
    block = re.search(r"```bash\n(.*?)```", text, flags=re.DOTALL).group(1)
    commands = [line for line in block.splitlines() if line.strip()]
    assert len(commands) <= 3  # REQ-9: at most three commands


def test_the_commands_of_the_readme_exist(repo_root: Path):
    assert (repo_root / "tools" / "setup_data.py").is_file()
    assert (repo_root / "src" / "redactech" / "ui" / "app.py").is_file()
    assert (repo_root / "workspace.example.toml").is_file()
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'redactech = "redactech.cli:app"' in pyproject
    assert "dev = [" in pyproject  # the "dev" extra the install command asks for


def test_the_cli_quick_start_uses_real_commands_and_options(repo_root: Path):
    import typer.main

    from redactech.cli import app

    # inspect the click command objects: the text of --help depends on colours and on rich
    root = typer.main.get_command(app)
    text = _readme(repo_root)
    quick = re.findall(r"^redactech (\S+)", text, flags=re.MULTILINE)
    assert {"workspace", "request", "review", "write", "check"} <= set(quick)
    for command in dict.fromkeys(quick):
        assert command in root.commands, command
    assert "init" in root.commands["workspace"].commands

    def options(name: str) -> set[str]:
        return {opt for param in root.commands[name].params for opt in param.opts}

    assert {"--mapping", "--version-policy", "--out"} <= options("request")
    assert "--accept-all" in options("review")


def test_the_readme_has_the_pipeline_diagram_and_the_doc_links(repo_root: Path):
    text = _readme(repo_root)
    for agent in ("A0", "A1", "A2", "A4", "A5", "A7", "A11"):
        assert agent in text.split("## Architecture")[1].split("```text")[1], agent
    order = [text.index(a) for a in ("A1 indexer", "A2 request", "A4 locator", "A5 preparer",
                                     "A7 checker", "A11 writer")]
    assert order == sorted(order)  # the diagram follows the pipeline order
    assert "Streamlit UI" in text
    for link in re.findall(r"\]\((docs/[A-Z_]+\.md)\)", text):
        assert (repo_root / link).is_file(), link


def test_the_readme_names_nothing_private(repo_root: Path):
    text = _readme(repo_root).lower()
    for word in ("customer", "client"):
        assert word not in text.replace("customer question", "")


def test_the_roadmap_lists_every_out_of_scope_item_and_the_known_gaps(repo_root: Path):
    text = (repo_root / "docs" / "ROADMAP_NEXT.md").read_text(encoding="utf-8")
    for item in ROADMAP_ITEMS + KNOWN_GAPS:
        assert item in text, item
    assert "http" not in text
