"""Tests of the scenario runner and of `redactech eval`: they must catch what they promise."""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from redactech.cli import app
from redactech.pipeline import scenarios as sc

TESTS = Path(__file__).resolve().parents[1]
LRU = "DMC-RTPROTO-AAA-D00-00-00-00AA"
runner = CliRunner()


def clone(tmp_path: Path, name: str = "lru1010", attendu=None, scenario=None) -> Path:
    """A copy of a scenario (with the fixtures and schemas it needs), optionally modified."""
    base = tmp_path / "tests"
    shutil.copytree(TESTS / "fixtures", base / "fixtures")
    shutil.copytree(TESTS / "scenarios" / "_schemas", base / "scenarios" / "_schemas")
    target = base / "scenarios" / name
    shutil.copytree(TESTS / "scenarios" / name, target)
    for file, change in (("attendu.yaml", attendu), ("scenario.yaml", scenario)):
        if change is not None:
            data = yaml.safe_load((target / file).read_text(encoding="utf-8"))
            change(data)
            (target / file).write_text(yaml.safe_dump(data), encoding="utf-8")
    return target


def run(directory: Path, tmp_path: Path, variant=None) -> sc.Result:
    return sc.run_scenario(directory, tmp_path / "work", variant)


def failures_of(result: sc.Result) -> str:
    return "\n".join(result.failures)


# --- the reference scenario passes ----------------------------------------------


def test_a_correct_attendu_passes_with_perfect_metrics(tmp_path: Path):
    result = run(clone(tmp_path), tmp_path)
    assert result.failures == [] and result.passed
    for name in ("exhaustiveness", "precision", "preservation", "validity", "traceability"):
        assert result.metrics[name] == 1.0, name
    assert result.introduced == 0 and result.metrics["seconds"] >= 0


# --- what it must catch ---------------------------------------------------------


def test_an_unexpected_change_is_reported_and_lowers_precision(tmp_path: Path):
    def drop_first(data):
        data["changes"] = data["changes"][1:]  # the comrep change is no longer expected

    result = run(clone(tmp_path, attendu=drop_first), tmp_path)
    assert not result.passed
    assert "unexpected change" in failures_of(result)
    assert result.metrics["precision"] < 1.0


def test_a_missing_change_is_reported_and_lowers_exhaustiveness(tmp_path: Path):
    def add_phantom(data):
        data["changes"].append(
            {
                "doc": f"{LRU}-0A3A-D_001-00_EN-US.XML",
                "scope_xpath": "//partSpec[partIdent/@partNumberValue='X2']",
                "marks": {"changeMark": "1", "changeType": "modify"},
            }
        )

    result = run(clone(tmp_path, attendu=add_phantom), tmp_path)
    assert not result.passed and "no element with the marks" in failures_of(result)
    assert result.metrics["exhaustiveness"] < 1.0


def test_an_expected_change_on_a_document_without_output_is_reported(tmp_path: Path):
    def other_doc(data):
        data["changes"].append({"doc": "DMC-NOT-WRITTEN.XML", "scope_xpath": "//x"})

    result = run(clone(tmp_path, attendu=other_doc), tmp_path)
    assert "no output was written" in failures_of(result)
    assert result.metrics["exhaustiveness"] < 1.0


def test_wrong_output_file_names_are_reported(tmp_path: Path):
    wrong = clone(tmp_path, attendu=lambda d: d.update(outputs=[f"{LRU}-0A3A-D_001-02_X"]))
    result = run(wrong, tmp_path)
    assert "output files" in failures_of(result)


def test_a_document_that_must_stay_untouched_but_is_written_is_reported(tmp_path: Path):
    def protect(data):
        data["unchanged"].append(f"{LRU}-040A-*")

    result = run(clone(tmp_path, attendu=protect), tmp_path)
    assert "must stay untouched" in failures_of(result)
    assert result.metrics["preservation"] < 1.0


def test_an_inconsistent_attendu_is_reported(tmp_path: Path):
    def wrong_before(data):
        data["changes"][0]["before_contains"] = ["not in the input"]

    result = run(clone(tmp_path, attendu=wrong_before), tmp_path)
    assert "attendu inconsistent" in failures_of(result)


def test_forbidden_text_still_in_the_output_is_reported(tmp_path: Path):
    def keep_old(data):
        data["changes"][0]["after_absent"] = ["Line replaceable unit"]

    result = run(clone(tmp_path, attendu=keep_old), tmp_path)
    assert "is still in the output" in failures_of(result)


def test_counts_blocked_proposals_and_time_are_checked(tmp_path: Path):
    result = run(clone(tmp_path, attendu=lambda d: d.update(blocked=1)), tmp_path)
    assert "blocked proposal" in failures_of(result)
    slow = run(clone(tmp_path / "s", scenario=lambda d: d.update(max_seconds=0)), tmp_path / "s")
    assert "too slow" in failures_of(slow)


def test_pre_existing_problems_are_counted_separately(tmp_path: Path):
    result = run(clone(tmp_path, "preexisting_brex"), tmp_path)
    assert result.passed, failures_of(result)
    assert result.introduced == 0 and result.pre_existing >= 1


def test_a_run_that_cannot_finish_is_a_failure_not_a_crash(tmp_path: Path):
    def nothing_accepted(data):
        data["decisions"] = {"auto_accept": False}

    result = run(clone(tmp_path, scenario=nothing_accepted), tmp_path)
    assert not result.passed and "the run failed" in failures_of(result)


# --- blocked proposals, baseline, illustrations, BREX swap ---------------------


def test_blocked_details_are_checked(tmp_path: Path):
    def wrong(data):
        data["blocked_details"] = [
            {"operation": "op-0001", "attempts": 2, "rule_xpath": "//other",
             "question_contains": ["never asked"]},
            {"operation": "op-0002"},
        ]

    result = run(clone(tmp_path, "forbidden_request", attendu=wrong), tmp_path)
    text = failures_of(result)
    assert "3 attempt(s), expected 2" in text and "//other is not shown" in text
    assert "no question contains" in text and "op-0002: no blocked proposal" in text


def test_the_baseline_brex_count_is_checked(tmp_path: Path):
    def too_many(data):
        data["variants"]["project"]["baseline_brex"] = {"min": 3}

    result = run(clone(tmp_path, "brex_swap", attendu=too_many), tmp_path, "project")
    assert "BREX failure(s) in the baseline, at least 3" in failures_of(result)


def test_an_unknown_figure_is_reported(tmp_path: Path):
    def wrong_figure(data):
        data["illustrations"][0]["figure_id"] = "fig-9999"

    result = run(clone(tmp_path, "ops_steps", attendu=wrong_figure), tmp_path)
    assert "fig-9999: no illustration zone" in failures_of(result)


def test_a_brex_patch_that_matches_nothing_is_a_failure(tmp_path: Path):
    def nothing(data):
        data["variants"][1]["brex_patch"]["old"] = "//not/in/the/brex"

    result = run(clone(tmp_path, "brex_swap", scenario=nothing), tmp_path, "swapped")
    assert "could not be prepared" in failures_of(result)


# --- markers, variants, report --------------------------------------------------


def test_a_scenario_without_its_data_is_skipped(tmp_path: Path):
    directory = clone(tmp_path, "lru1010_bike41")
    result = sc.run_scenario(directory, tmp_path / "work", repo_root=tmp_path)
    assert result.skipped and "data41" in result.skipped and not result.passed


def test_a_pending_scenario_is_skipped_even_with_data(tmp_path: Path):
    def pending(data):
        data.update(markers=[], pending="to write")

    directory = clone(tmp_path, "lru1010_bike41", scenario=pending)
    result = run(directory, tmp_path)
    assert result.skipped and "still to write" in result.skipped


def test_variants_override_the_expectations(tmp_path: Path):
    directory = clone(tmp_path, "versioning")
    assert sc.variants_of(directory) == ["none", "in_work", "new_issue"]
    outputs = {v: sc.load(directory, v)[1]["outputs"][0][-23:] for v in sc.variants_of(directory)}
    assert outputs == {
        "none": "520B-A_007-00_EN-US.XML",
        "in_work": "520B-A_007-01_EN-US.XML",
        "new_issue": "520B-A_008-00_EN-US.XML",
    }
    with pytest.raises(ValueError):
        sc.load(directory, "other")
    for variant in sc.variants_of(directory):
        result = run(directory, tmp_path / variant, variant)
        assert result.passed, f"{variant}: {failures_of(result)}"


def test_discover_ignores_support_folders(tmp_path: Path):
    (tmp_path / "_schemas").mkdir()
    (tmp_path / "empty").mkdir()
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "scenario.yaml").write_text("a: 1\n", encoding="utf-8")
    assert [d.name for d in sc.discover(tmp_path)] == ["ok"]


def test_the_report_is_a_markdown_table():
    good = sc.Result("a", metrics={"exhaustiveness": 1.0, "seconds": 0.5})
    bad = sc.Result("b", "v", failures=["boom"], introduced=2, pre_existing=1)
    skipped = sc.Result("c", skipped="missing data (data41)")
    text = sc.report_markdown([good, bad, skipped], datetime.date(2025, 3, 7))
    assert text.startswith("# Scenario evaluation 2025-03-07")
    assert "| a | PASS |" in text and "| b[v] | FAIL |" in text and "2 / 1" in text
    assert "| c | skipped: missing data (data41) |" in text and "- b[v]: boom" in text


# --- redactech eval -------------------------------------------------------------


def test_eval_runs_the_scenarios_and_writes_the_report(tmp_path: Path):
    out = tmp_path / "reports"
    result = runner.invoke(app, ["eval", str(TESTS / "scenarios"), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "PASS lru1010" in result.output and "PASS versioning[new_issue]" in result.output
    assert "SKIP lru1010_bike41" in result.output
    (report,) = out.glob("eval_*.md")
    text = report.read_text(encoding="utf-8")
    assert "| lru1010 | PASS |" in text and "| delete_mark | PASS |" in text


def test_eval_exits_1_when_a_scenario_fails(tmp_path: Path):
    directory = clone(tmp_path, attendu=lambda d: d.update(blocked=3))
    out = tmp_path / "reports"
    result = runner.invoke(app, ["eval", str(directory.parent), "--out", str(out)])
    assert result.exit_code == 1 and "FAIL lru1010" in result.output
    assert "blocked proposal" in result.output and list(out.glob("eval_*.md"))


def test_eval_needs_a_folder(tmp_path: Path):
    result = runner.invoke(app, ["eval", str(tmp_path / "absent")])
    assert result.exit_code == 1 and "no scenarios folder" in result.output
