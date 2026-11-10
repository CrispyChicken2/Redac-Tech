"""All the calls to a language model go through this package (REQ-8).

``get_provider(config)`` returns the provider named by ``[llm] provider`` in ``config.toml``:
``none`` (no model: callers use their code paths), ``ollama`` (a local Ollama server) or ``fake``
(recorded answers, for the tests). The model is one configuration line: ``[llm] model``.
"""

from __future__ import annotations

from pathlib import Path

from redactech.config import Config, LLMConfig
from redactech.llm.base import (
    LLMError,
    LLMOutputError,
    LLMProvider,
    LLMUnavailable,
    PromptTooLarge,
    RemoteLLMRefused,
)
from redactech.llm.fake import CassetteError, CassetteMissing, FakeLLM
from redactech.llm.none import NoLLM

PROVIDERS = ("none", "ollama", "fake")
DEFAULT_CASSETTES = Path("tests") / "llm_cassettes"

__all__ = [
    "CassetteError",
    "CassetteMissing",
    "FakeLLM",
    "LLMError",
    "LLMOutputError",
    "LLMProvider",
    "LLMUnavailable",
    "NoLLM",
    "PromptTooLarge",
    "RemoteLLMRefused",
    "get_provider",
]


def get_provider(
    config: Config | LLMConfig,
    *,
    log_path: Path | str | None = None,
    cassette_dir: Path | str | None = None,
) -> LLMProvider:
    """The provider of ``[llm] provider``; the model comes from ``[llm] model`` only."""
    llm = config.llm if isinstance(config, Config) else config
    name = llm.provider
    if name == "none":
        return NoLLM(llm, log_path)
    if name == "fake":
        return FakeLLM(cassette_dir or DEFAULT_CASSETTES, llm, log_path)
    if name == "ollama":
        from redactech.llm.ollama import OllamaProvider  # httpx is only loaded when used

        return OllamaProvider(llm, log_path)
    raise ValueError(f"unknown llm provider {name!r} (expected one of {', '.join(PROVIDERS)})")
