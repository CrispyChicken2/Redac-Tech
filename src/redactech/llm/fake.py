"""FakeLLM: recorded answers (cassettes) for the tests; it never touches a network.

A cassette is a JSON file in the cassette folder (``tests/llm_cassettes/``)::

    {"system": "...", "prompt": "...", "schema": "OperationList",
     "responses": [{"operations": []}, "text that is not JSON"]}

``responses`` are the successive answers to the same request: the first for the first attempt, the
next ones for the retries (the last one is repeated). A response is a JSON value or a plain text
(to test an invalid answer); ``response`` (one answer) is accepted too. The key of a cassette is
``sha256(system + prompt + schema name)``; a request without cassette raises ``CassetteMissing``
with that key.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from redactech.config import LLMConfig
from redactech.llm.base import LLMError, LLMProvider, Request


class CassetteMissing(LLMError):
    """No recorded answer for this request (the message holds the key to record it under)."""

    def __init__(self, key: str, schema_name: str = ""):
        super().__init__(f"no cassette for key {key} (schema {schema_name or '?'})")
        self.key = key


def cassette_key(system: str, prompt: str, schema_name: str) -> str:
    """The key of a request: sha256 of the system text, the prompt and the schema name."""
    return hashlib.sha256((system + prompt + schema_name).encode("utf-8")).hexdigest()


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(
        self,
        cassette_dir: Path | str,
        config: LLMConfig | None = None,
        log_path: Path | str | None = None,
    ):
        super().__init__(config, log_path)
        self.cassette_dir = Path(cassette_dir)
        self.calls: list[Request] = []  # what was asked, for the tests

    def _cassettes(self) -> dict[str, list[Any]]:
        found: dict[str, list[Any]] = {}
        if not self.cassette_dir.is_dir():
            return found
        for path in sorted(self.cassette_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            key = cassette_key(data.get("system", ""), data["prompt"], data["schema"])
            responses = data["responses"] if "responses" in data else [data["response"]]
            found[key] = list(responses)
        return found

    def _generate(self, request: Request) -> str:
        self.calls.append(request)
        key = cassette_key(request.system, request.prompt, request.schema_name)
        responses = self._cassettes().get(key)
        if not responses:
            raise CassetteMissing(key, request.schema_name)
        answer = responses[min(request.attempt, len(responses) - 1)]
        return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
