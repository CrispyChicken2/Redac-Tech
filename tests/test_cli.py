"""Tests of the CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from redactech.cli import app

runner = CliRunner()

COMMANDS = [
    "workspace", "index", "baseline", "request", "review", "write", "check", "render", "eval",
]


def click_commands() -> dict:
    """The click commands of the app: robust to colours and rich formatting of --help."""
    import typer.main

    return typer.main.get_command(app).commands


def test_help_lists_all_commands():
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert set(COMMANDS) <= set(click_commands())


def test_workspace_help_lists_subcommands():
    assert runner.invoke(app, ["workspace", "--help"]).exit_code == 0
    assert {"init", "add", "list"} <= set(click_commands()["workspace"].commands)


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


# --- request / review / write / check -----------------------------------------


CODE = "AAA-D00-00-00-00AA"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "s1000d"
LRU_FILES = (
    f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML",
    f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML",
    f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML",
    f"UPF-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML",
    f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML",
    f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML",
)


@pytest.fixture
def project(tmp_path: Path) -> dict:
    """A workspace over copies of the fixtures and a CSV mapping LRU1010 -> LRU2020."""
    src = tmp_path / "src"
    src.mkdir()
    for name in LRU_FILES:
        (src / name).write_bytes((FIXTURES / name).read_bytes())
    ws = tmp_path / "ws.toml"
    assert run("workspace", "init", "-w", str(ws)).exit_code == 0
    ws.write_text("", encoding="utf-8")
    folder = str(src)
    added = run("workspace", "add", folder, "--id", "fixtures", "--brex-dir", folder, "-w", str(ws))
    assert added.exit_code == 0, added.output
    mapping = tmp_path / "lots.csv"
    mapping.write_text("old;new;reason\nLRU1010;LRU2020;replaced\n", encoding="utf-8")
    return {"ws": str(ws), "mapping": str(mapping), "runs": str(tmp_path / "runs"), "src": src}


def request_args(project: dict, *extra: str) -> list[str]:
    return ["request", "--mapping", project["mapping"], "--out", project["runs"],
            "-w", project["ws"], *extra]


def the_run_dir(project: dict) -> Path:
    (folder,) = Path(project["runs"]).iterdir()
    return folder


def proposal_ids(output: str) -> list[str]:
    return [line.split("\t")[0] for line in output.splitlines() if "\t" in line]


def test_request_runs_to_the_proposals_and_prints_table_and_policy(project: dict):
    result = run(*request_args(project, "--version-policy", "in_work"))
    assert result.exit_code == 0, result.output
    assert "proposed" in result.output and "content/certain" in result.output
    assert "content/probable" in result.output
    assert "suggested version policy:" in result.output and "op-0001" in result.output
    assert "chosen version policy: in_work" in result.output
    assert len(proposal_ids(result.output)) >= 3
    assert (the_run_dir(project) / "state.json").is_file()
    assert not (the_run_dir(project) / "out").exists()  # nothing written without a decision


def test_request_without_mapping_or_with_a_bad_policy_fails(project: dict):
    no_mapping = run("request", "--out", project["runs"], "-w", project["ws"])
    assert no_mapping.exit_code == 1 and "--mapping" in no_mapping.output
    bad = run(*request_args(project, "--version-policy", "sometimes"))
    assert bad.exit_code == 1 and "unknown version policy" in bad.output
    assert not Path(project["runs"]).exists()


def test_auto_accept_is_a_hidden_option(project: dict):
    params = {p.name: p for p in click_commands()["request"].params}
    assert params["auto_accept"].hidden is True  # not shown in --help, usable by the tests


def test_review_lists_and_records_decisions_then_write_produces_the_documents(project: dict):
    first = run(*request_args(project))
    assert first.exit_code == 0
    folder = str(the_run_dir(project))
    listing = run("review", folder)
    assert listing.exit_code == 0 and "still to decide" in listing.output
    refused = run("write", folder, "--version-policy", "in_work")
    assert refused.exit_code == 1 and "undecided" in refused.output
    assert not (the_run_dir(project) / "out").exists()
    accepted = run("review", folder, "--accept-all")
    assert accepted.exit_code == 0 and "accepted: " in accepted.output
    (free,) = [
        line.split("\t")[0] for line in accepted.output.splitlines()
        if "content/probable" in line and "\tproposed\t" in line
    ]
    rejected = run("review", folder, "--reject", free, "--reason", "leave the text")
    assert rejected.exit_code == 0 and "no alternative" in rejected.output
    no_policy = run("write", folder)
    assert no_policy.exit_code == 1 and "--version-policy" in no_policy.output
    written = run("write", folder, "--version-policy", "in_work")
    assert written.exit_code == 0, written.output
    assert "2 file(s) written" in written.output
    out = the_run_dir(project) / "out"
    assert len(list(out.glob("*.XML"))) == 2
    assert all("LRU2020" in f.read_text(encoding="utf-8") for f in out.glob("*.XML"))


def test_pending_decision_and_unknown_proposal(project: dict):
    run(*request_args(project))
    folder = str(the_run_dir(project))
    ok = run("review", folder, "--pending", "nope")
    assert ok.exit_code == 1 and "unknown proposal" in ok.output
    missing = run("review", str(the_run_dir(project) / "absent"))
    assert missing.exit_code == 1 and "not a run folder" in missing.output


def test_end_to_end_with_auto_accept_and_check(project: dict):
    result = run(*request_args(project, "--version-policy", "in_work", "--auto-accept"))
    assert result.exit_code == 0, result.output
    assert "auto-accepted: " in result.output
    assert "1 proposal(s) to decide" in result.output  # the free text is never automatic
    folder = str(the_run_dir(project))
    (free,) = [
        line.split("\t")[0] for line in result.output.splitlines()
        if "\tproposed\t" in line and "content/probable" in line
    ]
    assert run("review", folder, "--accept", free).exit_code == 0
    written = run("write", folder)  # the policy was given to `request`
    assert written.exit_code == 0 and "3 file(s) written" in written.output
    for name in ("report.json", "report.html", "questions.csv", "decisions.jsonl"):
        assert f"delivery {the_run_dir(project) / name}" in written.output
        assert (the_run_dir(project) / name).is_file()
    checked = run("check", str(the_run_dir(project) / "out"))
    assert checked.exit_code == 0, checked.output
    assert "checked 3 file(s), 0 introduced error(s)" in checked.output


def test_check_needs_a_run_folder(tmp_path: Path):
    (tmp_path / "out").mkdir()
    result = run("check", str(tmp_path / "out"))
    assert result.exit_code == 1 and "not a run folder" in result.output


# --- render ---------------------------------------------------------------------------------

MARKED_DM = FIXTURES / f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
DELETED_TEXT = "Step marked as deleted but still present."


def test_render_prints_a_self_contained_page_with_both_views():
    result = run("render", str(MARKED_DM))
    assert result.exit_code == 0, result.output
    page = result.output
    assert page.startswith("<!DOCTYPE html>") and "<style>" in page
    assert 'class="rt-side"' in page and 'class="rt-xml"' in page and 'class="rt-doc"' in page
    assert "rt-line rt-add" in page and "rt-step rt-add" in page
    assert "<script" not in page.lower() and DELETED_TEXT in page


def test_render_one_view_at_a_time():
    xml = run("render", str(MARKED_DM), "--view", "xml").output
    assert 'class="rt-xml"' in xml and 'class="rt-doc"' not in xml
    published = run("render", str(MARKED_DM), "--view", "published").output
    assert 'class="rt-doc"' in published and 'class="rt-xml"' not in published


def test_render_hides_deleted_elements_on_request():
    shown = run("render", str(MARKED_DM), "--view", "published", "--show-deleted").output
    hidden = run("render", str(MARKED_DM), "--view", "published", "--hide-deleted").output
    assert DELETED_TEXT in shown and DELETED_TEXT not in hidden


def test_render_writes_a_file_with_out(tmp_path: Path):
    target = tmp_path / "pages" / "dm.html"
    result = run("render", str(MARKED_DM), "--out", str(target))
    assert result.exit_code == 0 and f"written {target}" in result.output
    assert "<!DOCTYPE html>" not in result.output  # the page went to the file
    assert target.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_render_refuses_a_bad_view_a_missing_file_and_bad_xml(tmp_path: Path):
    bad_view = run("render", str(MARKED_DM), "--view", "pdf")
    assert bad_view.exit_code == 1 and "unknown view" in bad_view.output
    missing = run("render", str(tmp_path / "absent.xml"))
    assert missing.exit_code == 1 and "no document" in missing.output
    broken = tmp_path / "broken.xml"
    broken.write_text("<dmodule><unclosed></dmodule>", encoding="utf-8")
    result = run("render", str(broken))
    assert result.exit_code == 1 and "cannot render" in result.output


def test_render_leaves_the_document_untouched():
    before = MARKED_DM.read_bytes()
    run("render", str(MARKED_DM))
    assert MARKED_DM.read_bytes() == before


# --- request --text ---------------------------------------------------------------------------

CASSETTES = Path(__file__).resolve().parent / "llm_cassettes"


@pytest.fixture
def recorded_model(monkeypatch):
    """The pipeline reads free text with the recorded answers, never a real model."""
    from redactech.llm import FakeLLM
    from redactech.pipeline import orchestrator

    monkeypatch.setattr(orchestrator, "get_provider", lambda config: FakeLLM(CASSETTES))


def text_args(project: dict, text: str, *extra: str) -> list[str]:
    return ["request", "--text", text, "--out", project["runs"], "-w", project["ws"], *extra]


def test_a_free_text_request_runs_to_the_proposals(project: dict, recorded_model):
    text = "Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation."
    result = run(*text_args(project, text, "--version-policy", "in_work"))
    assert result.exit_code == 0, result.output
    assert "content/certain" in result.output and "content/probable" in result.output
    assert "question (free text)" not in result.output
    assert "free_text" in (the_run_dir(project) / "request.json").read_text(encoding="utf-8")


def test_an_invented_value_is_printed_as_a_question(project: dict, recorded_model):
    result = run(*text_args(project, "Replace the part LRU1010 by its successor."))
    assert result.exit_code == 0, result.output
    assert "question (free text):" in result.output and "LRU9999" in result.output
    assert "no proposal" in result.output


def test_free_text_without_a_model_is_refused(project: dict):
    result = run(*text_args(project, "Replace the part LRU1010 by its successor."))
    assert result.exit_code == 1 and "local model" in result.output
    assert not Path(project["runs"]).exists()


def test_give_the_mapping_or_the_text_but_not_both_or_none(project: dict):
    both = run(*request_args(project), "--text", "Replace A by B")
    assert both.exit_code == 1 and "not both" in both.output
    neither = run("request", "--out", project["runs"], "-w", project["ws"])
    assert neither.exit_code == 1 and "--mapping" in neither.output and "--text" in neither.output


def test_the_text_option_exists(project: dict):
    import typer.main

    params = {p.name: p for p in typer.main.get_command(app).commands["request"].params}
    assert params["text"].opts == ["--text"] and not params["text"].hidden


def test_write_warns_about_the_open_customer_questions(project: dict):
    assert run(*request_args(project)).exit_code == 0
    folder = str(the_run_dir(project))
    accepted = run("review", folder, "--accept-all")
    (free,) = [
        line.split("\t")[0] for line in accepted.output.splitlines()
        if "content/probable" in line and "\tproposed\t" in line
    ]
    held = run("review", folder, "--pending", free, "--comment", "Ask the customer")
    assert held.exit_code == 0, held.output
    written = run("write", folder, "--version-policy", "in_work")
    assert written.exit_code == 0, written.output
    assert "warning: 1 question client ouverte (en attente)" in written.output
    assert "Ask the customer" in written.output


def test_review_can_take_a_decision_back(project: dict):
    assert run(*request_args(project)).exit_code == 0
    folder = str(the_run_dir(project))
    accepted = run("review", folder, "--accept-all")
    (line,) = [x for x in accepted.output.splitlines() if x.startswith("accepted: ")]
    target = line.removeprefix("accepted: ").split(", ")[0]
    again = run("review", folder, "--reject", target, "--reason", "no")
    assert again.exit_code == 1 and "reopen" in again.output  # a decision is final
    reopened = run("review", folder, "--reopen", target)
    assert reopened.exit_code == 0, reopened.output
    assert f"reopened {target}: proposed" in reopened.output
    missing = run("review", folder, "--reopen", target)
    assert missing.exit_code == 1 and "not decided" in missing.output
