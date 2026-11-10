"""NoLLM: the provider used when no model is configured; callers fall back to their code paths."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from redactech.llm.base import LLMProvider, LLMUnavailable, Request


class NoLLM(LLMProvider):
    """Always unavailable: ``complete_json`` raises ``LLMUnavailable`` without doing anything."""

    name = "none"

    def complete_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        *,
        system: str = "",
        examples: Sequence[tuple[str, Any]] = (),
    ) -> BaseModel:
        raise LLMUnavailable('no language model is configured ([llm] provider = "none")')

    def _generate(self, request: Request) -> str:  # pragma: no cover - never reached
        raise LLMUnavailable("no language model is configured")
