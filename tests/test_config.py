"""Tests of the configuration loader."""

from __future__ import annotations

from pathlib import Path

from redactech.config import Config, load_config


def test_defaults_without_file(tmp_path: Path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg == Config()
    assert cfg.llm.provider == "none"
    assert cfg.llm.model == "ministral-3:8b"
    assert cfg.llm.max_retries == 2 and cfg.llm.timeout_s == 120
    assert cfg.trace.default_version_policy == "ask"
    assert cfg.trace.delete_mode == "mark" and cfg.trace.max_rule_retries == 2
    assert cfg.workspace.file == "workspace.toml"


def test_file_overrides_and_keeps_other_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[llm]\nprovider = "ollama"\nmodel = "other:1b"\n\n[trace]\nmax_alternatives = 5\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.llm.provider == "ollama" and cfg.llm.model == "other:1b"
    assert cfg.llm.timeout_s == 120
    assert cfg.trace.max_alternatives == 5 and cfg.trace.consolidate_on_new_issue is True


def test_repo_config_toml_matches_defaults(repo_root: Path):
    assert load_config(repo_root / "config.toml") == Config()


def test_default_path_is_cwd_config(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text('[llm]\nprovider = "ollama"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert load_config().llm.provider == "ollama"
