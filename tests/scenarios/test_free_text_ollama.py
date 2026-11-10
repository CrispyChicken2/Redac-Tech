"""The free-text scenarios with the REAL local model (skipped unless REDACTECH_OLLAMA=1).

The expectations are the same as with the recorded answers: whatever the model says, the code
must give the same result for a clear request, and never write an invented value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.llm.ollama import OllamaProvider
from redactech.pipeline import scenarios

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]


@pytest.fixture(scope="module")
def provider():
    with OllamaProvider() as llm:
        assert llm.ensure_model()
        yield llm


@pytest.mark.ollama
@pytest.mark.parametrize("name", ["free_text_fr", "free_text_en"])
def test_a_clear_request_gives_the_same_result_as_the_mapping(name: str, provider, tmp_path: Path):
    result = scenarios.run_scenario(HERE / name, tmp_path / "work", repo_root=REPO_ROOT,
                                    provider=provider)
    assert result.failures == [], result.failures
    assert result.metrics["exhaustiveness"] == 1.0 and result.metrics["precision"] == 1.0


@pytest.mark.ollama
def test_an_incomplete_request_never_writes_an_invented_value(provider, tmp_path: Path):
    """The request names no successor: the model may ask, or invent; the code must not write."""
    result = scenarios.run_scenario(HERE / "hallucination_trap", tmp_path / "work",
                                    repo_root=REPO_ROOT, provider=provider)
    # the recorded answer invents LRU9999 and the check expects that question; a real model may
    # ask something else, so only the safety failures count here
    unsafe = [f for f in result.failures if "free-text question" not in f]
    assert unsafe == [], unsafe
