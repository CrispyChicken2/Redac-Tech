"""The end-to-end scenarios: one test per scenario (and variant), compared with attendu.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.pipeline import scenarios

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
CASES = [(d, v) for d in scenarios.discover(HERE) for v in scenarios.variants_of(d)]
IDS = [d.name if v is None else f"{d.name}-{v}" for d, v in CASES]
METRICS = ("exhaustiveness", "precision", "preservation", "validity", "traceability")


@pytest.mark.parametrize(("directory", "variant"), CASES, ids=IDS)
def test_scenario(directory: Path, variant: str | None, tmp_path: Path):
    result = scenarios.run_scenario(directory, tmp_path / "work", variant, repo_root=REPO_ROOT)
    if result.skipped:
        pytest.skip(result.skipped)
    assert result.failures == []
    assert {name: result.metrics[name] for name in METRICS} == dict.fromkeys(METRICS, 1.0)


def test_the_expected_scenarios_exist():
    names = {d.name for d in scenarios.discover(HERE)}
    expected = {"lru1010", "lru1010_bike41", "delete_mark", "versioning", "preexisting_brex"}
    expected |= {"batch20", "batch20_bike41", "ops_steps", "forbidden_request", "brex_swap"}
    expected |= {"free_text_fr", "free_text_en", "hallucination_trap"}
    assert expected <= names
    assert [d.name for d in scenarios.discover(HERE) if d.name.startswith("_")] == []
    versioning = HERE / "versioning"
    assert scenarios.variants_of(versioning) == ["none", "in_work", "new_issue"]


def test_the_batch_scenarios_ask_for_twenty_parts_in_under_ten_seconds():
    for name in ("batch20", "batch20_bike41"):
        scenario, attendu = scenarios.load(HERE / name)
        assert len(scenario["request"]["mapping"]) == 20 and scenario["max_seconds"] == 10
        assert len(attendu["changes"]) >= 20
    assert scenarios.load(HERE / "batch20_bike41")[0]["markers"] == ["data41"]
    assert scenarios.variants_of(HERE / "brex_swap") == ["project", "swapped"]
