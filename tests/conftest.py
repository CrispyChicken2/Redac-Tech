"""Shared fixtures and automatic skipping of environment-dependent tests."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _skip_reason(item: pytest.Item) -> str | None:
    if item.get_closest_marker("data41") and not (REPO_ROOT / "data/s1000d-4.1/bike").is_dir():
        return "data/s1000d-4.1/bike is missing (see data/README.md)"
    if item.get_closest_marker("data42") and not (REPO_ROOT / "data/s1000d-4.2/bike").is_dir():
        return "data/s1000d-4.2/bike is missing (see data/README.md)"
    if item.get_closest_marker("ollama") and os.environ.get("REDACTECH_OLLAMA") != "1":
        return "Ollama tests need REDACTECH_OLLAMA=1 and a local Ollama server"
    if item.get_closest_marker("ui") and importlib.util.find_spec("streamlit") is None:
        return "streamlit is not importable"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        reason = _skip_reason(item)
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "s1000d"


@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "test_run"
    run_dir.mkdir(parents=True)
    return run_dir
