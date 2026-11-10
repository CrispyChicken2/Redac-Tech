"""Tests of redactech.llm.get_provider: the provider and the model come from the configuration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from redactech.config import Config, LLMConfig, load_config
from redactech.llm import FakeLLM, NoLLM, get_provider
from redactech.llm.ollama import OllamaProvider

SRC = Path(__file__).resolve().parents[2] / "src"
CASSETTES = Path(__file__).resolve().parents[1] / "llm_cassettes"


def test_the_default_configuration_has_no_model():
    provider = get_provider(Config())
    assert isinstance(provider, NoLLM) and provider.name == "none"


def test_none_fake_and_ollama_are_chosen_by_the_provider_key():
    assert isinstance(get_provider(Config(llm=LLMConfig(provider="none"))), NoLLM)
    fake = get_provider(Config(llm=LLMConfig(provider="fake")), cassette_dir=CASSETTES)
    assert isinstance(fake, FakeLLM) and fake.cassette_dir == CASSETTES
    ollama = get_provider(Config(llm=LLMConfig(provider="ollama")))
    assert isinstance(ollama, OllamaProvider) and ollama.base_url == "http://localhost:11434"


def test_an_llm_section_alone_is_accepted_too():
    assert isinstance(get_provider(LLMConfig(provider="fake"), cassette_dir=CASSETTES), FakeLLM)


def test_an_unknown_provider_is_refused():
    with pytest.raises(ValueError, match="unknown llm provider 'gpt'"):
        get_provider(Config(llm=LLMConfig(provider="gpt")))


def test_the_model_is_one_configuration_line():
    for provider in ("fake", "ollama"):
        a = LLMConfig(provider=provider, model="model-a:1b")
        b = LLMConfig(provider=provider, model="model-b:7b")
        first = get_provider(a, cassette_dir=CASSETTES)
        second = get_provider(b, cassette_dir=CASSETTES)
        assert (first.model, second.model) == ("model-a:1b", "model-b:7b")
        assert first.temperature == second.temperature == 0.0
    assert get_provider(Config()).model == "ministral-3:8b"  # the default line


def test_the_provider_reads_config_toml(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[llm]\nprovider = "fake"\nmodel = "from-file:3b"\ntemperature = 0\nmax_retries = 4\n',
        encoding="utf-8",
    )
    provider = get_provider(load_config(path), cassette_dir=CASSETTES)
    assert isinstance(provider, FakeLLM)
    assert (provider.model, provider.max_retries, provider.temperature) == ("from-file:3b", 4, 0.0)


def test_the_repository_configuration_does_not_use_a_model(repo_root: Path):
    config = load_config(repo_root / "config.toml")
    assert config.llm.provider == "none" and config.llm.model == "ministral-3:8b"
    assert isinstance(get_provider(config), NoLLM)


def test_the_log_path_reaches_the_provider(tmp_path: Path):
    log = tmp_path / "llm_calls.jsonl"
    assert get_provider(Config(), log_path=log).log_path == log
    fake = get_provider(LLMConfig(provider="fake"), log_path=log, cassette_dir=CASSETTES)
    assert fake.log_path == log


def test_importing_the_package_does_not_load_the_http_client():
    code = "import sys, redactech.llm; print('httpx' in sys.modules)"
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "False"
