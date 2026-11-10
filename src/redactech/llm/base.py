"""LLM layer, shared part: the provider contract and the logic every provider shares.

``LLMProvider.complete_json(prompt, schema, *, system, examples)`` returns a validated instance of a
pydantic model. The model never writes a document: its answer is a typed JSON object, checked here
before anyone uses it. What is shared:

* the temperature comes from the configuration (``[llm] temperature``);
* the JSON is constrained by the schema: ``schema.model_json_schema()`` is handed to the provider;
* the answer is validated; on an invalid answer the model is asked again, at most ``max_retries``
  times (``[llm] max_retries``), with the validation error added to the conversation;
* a call whose prompt is estimated at 6,000 tokens or more (characters / 4) is refused before
  anything is sent (``PromptTooLarge``);
* every attempt is logged, one JSON line, to ``runs/<id>/llm_calls.jsonl`` when a log path is
  given: time, provider, model, a hash of the prompt (never the prompt), attempt number, duration,
  ok or the error. No secret is ever written.

Concrete providers only implement ``_generate`` (one round trip returning the raw text).
"""

from __future__ import annotations

import abc
import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from redactech.config import LLMConfig

MAX_PROMPT_TOKENS = 6000
MAX_REINJECTED = 2000  # characters of an invalid answer put back in the conversation
RETRY_REQUEST = (
    "Your previous answer was not valid: {error}\n"
    "Answer again with one JSON object that follows the schema, and nothing else."
)
JSON_ONLY = "Answer with one JSON object that follows the given JSON schema, and nothing else."


class LLMError(Exception):
    """Base class of the errors of the LLM layer."""


class PromptTooLarge(LLMError):
    """The prompt is too long for one call (6,000 tokens estimated)."""


class LLMUnavailable(LLMError):
    """No model can answer (no provider, no server, no model): callers use their code path."""


class LLMOutputError(LLMError):
    """The model kept returning invalid JSON after the allowed retries."""


class RemoteLLMRefused(LLMError):
    """The model server is not on this machine and remote use was not allowed."""


@dataclass
class Request:
    """One round trip to the model, as the providers see it."""

    system: str
    prompt: str  # the original user prompt (what the cassette key is made of)
    messages: list[dict[str, str]]
    schema_json: dict[str, Any]
    schema_name: str
    attempt: int = 0  # 0 for the first answer, 1.. for the retries
    temperature: float = 0.0
    model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def estimate_tokens(*texts: str) -> int:
    """Rough token count: one token per four characters (rounded up)."""
    return -(-sum(len(t) for t in texts) // 4)


def check_size(messages: Sequence[dict[str, str]], schema_json: dict[str, Any]) -> int:
    """The estimated tokens of a call; ``PromptTooLarge`` at 6,000 or more."""
    used = estimate_tokens(json.dumps(list(messages), ensure_ascii=False), json.dumps(schema_json))
    if used >= MAX_PROMPT_TOKENS:
        raise PromptTooLarge(f"the prompt is about {used} tokens, the limit is {MAX_PROMPT_TOKENS}")
    return used


def prompt_hash(messages: Sequence[dict[str, str]]) -> str:
    """Hash of a conversation, for the log: it identifies a prompt without storing it."""
    data = json.dumps(list(messages), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _example_text(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class LLMProvider(abc.ABC):
    """A source of typed JSON answers (see the module docstring)."""

    name = "base"

    def __init__(self, config: LLMConfig | None = None, log_path: Path | str | None = None):
        self.config = config or LLMConfig()
        self.log_path = Path(log_path) if log_path is not None else None

    # --- what the configuration decides ------------------------------------------------------

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def temperature(self) -> float:
        return float(self.config.temperature)

    @property
    def max_retries(self) -> int:
        return int(self.config.max_retries)

    def close(self) -> None:
        """Release what the provider holds (a connection pool, ...). Nothing by default."""

    def __enter__(self) -> LLMProvider:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- the contract ------------------------------------------------------------------------

    @abc.abstractmethod
    def _generate(self, request: Request) -> str:
        """One round trip: the raw text the model answered (expected to be JSON)."""

    def build_messages(
        self, prompt: str, system: str = "", examples: Sequence[tuple[str, Any]] = ()
    ) -> list[dict[str, str]]:
        """The conversation: system, the worked examples as user/assistant turns, the prompt."""
        messages = [{"role": "system", "content": (system + "\n\n" + JSON_ONLY).strip()}]
        for question, answer in examples:
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": _example_text(answer)})
        messages.append({"role": "user", "content": prompt})
        return messages

    def complete_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        *,
        system: str = "",
        examples: Sequence[tuple[str, Any]] = (),
    ) -> BaseModel:
        """A validated ``schema`` instance for ``prompt`` (see the module docstring)."""
        schema_json = schema.model_json_schema()
        messages = self.build_messages(prompt, system, examples)
        check_size(messages, schema_json)
        error = ""
        for attempt in range(self.max_retries + 1):
            request = Request(
                system=system,
                prompt=prompt,
                messages=list(messages),
                schema_json=schema_json,
                schema_name=schema.__name__,
                attempt=attempt,
                temperature=self.temperature,
                model=self.model,
            )
            started = time.perf_counter()
            raw = ""
            try:
                raw = self._generate(request)
                result = schema.model_validate_json(raw)
            except ValidationError as exc:
                error = _short(describe(exc))
            except LLMError as exc:
                self._log(request, started, f"{type(exc).__name__}: {_short(str(exc))}")
                raise
            else:
                self._log(request, started, None)
                return result
            self._log(request, started, error)
            if attempt < self.max_retries:  # the conversation grows: it must still fit
                shown = raw if len(raw) <= MAX_REINJECTED else raw[:MAX_REINJECTED] + "…"
                messages.append({"role": "assistant", "content": shown})
                messages.append({"role": "user", "content": RETRY_REQUEST.format(error=error)})
                check_size(messages, schema_json)
        raise LLMOutputError(
            f"no valid answer after {self.max_retries + 1} attempt(s): {error}"
        )

    # --- local log ---------------------------------------------------------------------------

    def _log(self, request: Request, started: float, error: str | None) -> None:
        if self.log_path is None:
            return
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "provider": self.name,
            "model": self.model,
            "schema": request.schema_name,
            "prompt_sha256": prompt_hash(request.messages),
            "attempt": request.attempt,
            "duration_s": round(time.perf_counter() - started, 3),
            "ok": error is None,
            "error": error,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def describe(exc: ValidationError) -> str:
    """The validation errors as ``path: message`` lines, without echoing the offending input."""
    parts = []
    for item in exc.errors():
        where = ".".join(str(part) for part in item["loc"]) or "answer"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def _short(text: str, limit: int = 400) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[:limit] + "…"
