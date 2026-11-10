"""OllamaProvider: a model served by Ollama on this machine (``http://localhost:11434/api/chat``).

The request carries ``format`` = the JSON schema of the expected answer and
``options.temperature`` (``[llm] temperature``). Only the local machine is allowed as a host
(``localhost``, ``127.0.0.1``, ``::1``); any other host is refused with ``RemoteLLMRefused``
unless the environment variable ``REDACTECH_ALLOW_REMOTE_LLM`` is ``1``. Nothing is downloaded
by importing this module or by building the provider: ``ensure_model()`` tries ``ollama pull``
once, and only when a caller asks for it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx

from redactech.config import LLMConfig
from redactech.llm.base import LLMProvider, LLMUnavailable, RemoteLLMRefused, Request

DEFAULT_URL = "http://localhost:11434"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
ALLOW_REMOTE_ENV = "REDACTECH_ALLOW_REMOTE_LLM"


def check_host(url: str) -> str:
    """The URL if its host is this machine (or remote use is allowed), else ``RemoteLLMRefused``."""
    host = (urlparse(url).hostname or "").lower()
    if host in LOCAL_HOSTS or os.environ.get(ALLOW_REMOTE_ENV) == "1":
        return url.rstrip("/")
    raise RemoteLLMRefused(
        f"host {host or url!r} is not this machine; set {ALLOW_REMOTE_ENV}=1 to allow it"
    )


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        config: LLMConfig | None = None,
        log_path: Path | str | None = None,
        base_url: str = DEFAULT_URL,
        client: httpx.Client | None = None,
    ):
        super().__init__(config, log_path)
        self.base_url = check_host(base_url)
        self._client = client
        self._pull_tried = False

    def close(self) -> None:
        """Close the HTTP client (also when it was handed in)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.config.timeout_s)
        return self._client

    def _generate(self, request: Request) -> str:
        check_host(self.base_url)
        body = {
            "model": request.model or self.model,
            "messages": request.messages,
            "stream": False,
            "format": request.schema_json,
            "options": {"temperature": request.temperature},
        }
        try:
            response = self._http().post(f"{self.base_url}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Ollama does not answer at {self.base_url}: {exc}") from exc
        if response.status_code != 200:
            raise LLMUnavailable(f"Ollama answered HTTP {response.status_code}")
        try:
            return str(response.json()["message"]["content"])
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMUnavailable(f"unexpected answer from Ollama: {exc}") from exc

    def has_model(self) -> bool:
        """Is the configured model already known to the server? (``GET /api/tags``)"""
        try:
            response = self._http().get(f"{self.base_url}/api/tags")
            names = [m.get("name", "") for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        wanted = self.model
        return any(n == wanted or n.split(":")[0] == wanted for n in names)

    def ensure_model(self) -> bool:
        """Make the model available: ``ollama pull`` is tried ONCE, only when this is called.

        Returns True when the model is there afterwards. Never called at import or in tests.
        """
        if self.has_model():
            return True
        if self._pull_tried:
            return False
        self._pull_tried = True
        if shutil.which("ollama") is None:
            return False
        try:
            done = subprocess.run(
                ["ollama", "pull", self.model],
                check=False,
                capture_output=True,
                timeout=self.config.timeout_s * 10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0 and self.has_model()
