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
    assert {"lru1010", "lru1010_bike41", "delete_mark", "versioning", "preexisting_brex"} <= names
    assert [d.name for d in scenarios.discover(HERE) if d.name.startswith("_")] == []
    versioning = HERE / "versioning"
    assert scenarios.variants_of(versioning) == ["none", "in_work", "new_issue"]
