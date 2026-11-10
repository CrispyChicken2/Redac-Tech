"""FakeLLM: recorded answers (cassettes) for the tests; it never touches a network.

A cassette is a JSON file in the cassette folder (``tests/llm_cassettes/``)::

    {"system": "...", "prompt": "...", "schema": "OperationList",
     "responses": [{"operations": []}, "text that is not JSON"]}

``responses`` are the successive answers to the same request: the first for the first attempt, the
next ones for the retries (the last one is repeated). A response is a JSON value or a plain text
(to test an invalid answer); ``response`` (one answer) is accepted too. The key of a cassette is
``sha256(system + prompt + schema name)``; a request without cassette raises ``CassetteMissing``
with that key. Two cassettes with the same key raise ``CassetteError``.

A cassette that is easier to write by hand has ``prompt_contains`` (a piece of the user prompt)
instead of ``prompt``: it answers every request of its ``schema`` whose prompt contains that text
(and whose system text equals ``system`` when the cassette gives one); an exact key wins, and two
loose cassettes matching the same request raise ``CassetteError``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from redactech.config import LLMConfig
from redactech.llm.base import LLMError, LLMProvider, Request


class CassetteError(LLMError):
    """The cassettes themselves are wrong (two with the same key, or several that match)."""


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

    def _load(self) -> tuple[dict[str, tuple[str, list[Any]]], list[dict[str, Any]]]:
        """Exact cassettes by key (with their file), and the ``prompt_contains`` ones."""
        exact: dict[str, tuple[str, list[Any]]] = {}
        loose: list[dict[str, Any]] = []
        if not self.cassette_dir.is_dir():
            return exact, loose
        for path in sorted(self.cassette_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            responses = list(data["responses"] if "responses" in data else [data["response"]])
            if "prompt_contains" in data:
                loose.append({**data, "responses": responses, "file": path.name})
                continue
            key = cassette_key(data.get("system", ""), data["prompt"], data["schema"])
            if key in exact:
                first = exact[key][0]
                raise CassetteError(f"duplicate cassette key {key}: {first} and {path.name}")
            exact[key] = (path.name, responses)
        return exact, loose

    def _find(self, request: Request, key: str) -> list[Any] | None:
        exact, loose = self._load()
        if key in exact:
            return exact[key][1]
        found = [
            c for c in loose
            if c["schema"] == request.schema_name
            and c["prompt_contains"] in request.prompt
            and c.get("system", request.system) == request.system
        ]
        if len(found) > 1:
            names = ", ".join(c["file"] for c in found)
            raise CassetteError(f"several cassettes match the request: {names}")
        return found[0]["responses"] if found else None

    def _generate(self, request: Request) -> str:
        self.calls.append(request)
        key = cassette_key(request.system, request.prompt, request.schema_name)
        responses = self._find(request, key)
        if not responses:
            raise CassetteMissing(key, request.schema_name)
        answer = responses[min(request.attempt, len(responses) - 1)]
        return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
