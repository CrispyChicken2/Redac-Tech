"""Network guard: every LLM call lives in src/redactech/llm/ (REQ-8); no hosted LLM SDK anywhere."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "redactech"
LLM = SRC / "llm"

# modules that open connections
NETWORK = (
    "httpx", "requests", "urllib", "urllib3", "aiohttp", "http.client", "socket", "websockets",
    "websocket", "ftplib", "smtplib", "telnetlib", "xmlrpc", "grpc",
)
# hosted language model SDKs
HOSTED = (
    "openai", "anthropic", "google.generativeai", "google.genai", "cohere", "mistralai",
    "langchain", "litellm", "huggingface_hub", "replicate", "boto3", "vertexai", "groq",
)


def imports_of(text: str, names: tuple[str, ...]) -> list[str]:
    """The modules of ``names`` that the source imports (import statements only)."""
    found: list[str] = []
    for name in names:
        pattern = rf"^\s*(?:import|from)\s+{re.escape(name)}(?:[\s.,;]|$)"
        if re.search(pattern, text, flags=re.MULTILINE):
            found.append(name)
    return found


def python_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*.py") if "__pycache__" not in p.parts)


def outside_llm() -> list[Path]:
    return [p for p in python_files(SRC) if LLM not in p.parents]


# --- the detector itself ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("import httpx\n", ["httpx"]),
        ("    import requests as r\n", ["requests"]),
        ("from urllib.request import urlopen\n", ["urllib"]),
        ("from urllib import parse\n", ["urllib"]),
        ("import socket, os\n", ["socket"]),
        ("from http.client import HTTPSConnection\n", ["http.client"]),
        ("import json\nfrom pathlib import Path\n", []),
        ("# import httpx in a comment\n", []),
        ("text = 'import httpx'\n", []),
        ("import httpx_like_name_is_a_different_module\n", []),
    ],
)
def test_the_detector_finds_imports_and_only_imports(text: str, names: list[str]):
    assert imports_of(text, NETWORK) == names


# --- the source tree ---------------------------------------------------------------------------


def test_the_source_tree_is_found():
    assert (SRC / "config.py").is_file() and LLM.is_dir()
    assert len(outside_llm()) > 30  # the guard looks at the whole package


def test_no_network_module_is_used_outside_the_llm_package():
    offenders = {
        str(p.relative_to(SRC)): imports_of(p.read_text(encoding="utf-8"), NETWORK)
        for p in outside_llm()
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_in_the_llm_package_only_the_ollama_module_talks_to_a_server():
    users = {
        p.name: imports_of(p.read_text(encoding="utf-8"), ("httpx", "requests", "socket"))
        for p in python_files(LLM)
    }
    assert {k: v for k, v in users.items() if v} == {"ollama.py": ["httpx"]}


def test_no_hosted_llm_sdk_is_imported_anywhere():
    for folder in (SRC, SRC.parents[1] / "tools"):
        for path in python_files(folder):
            found = imports_of(path.read_text(encoding="utf-8"), HOSTED)
            assert found == [], f"{path.name}: {found}"


def test_the_only_address_in_the_llm_package_is_this_machine():
    pattern = re.compile(r"https?://[^\s\"'`)>]+")
    for path in python_files(LLM):
        for url in pattern.findall(path.read_text(encoding="utf-8")):
            assert re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])([:/]|$)", url), (path, url)


def test_the_ollama_module_guards_its_host_and_never_pulls_at_import():
    text = (LLM / "ollama.py").read_text(encoding="utf-8")
    assert "REDACTECH_ALLOW_REMOTE_LLM" in text and "RemoteLLMRefused" in text
    # the only subprocess call is inside ensure_model()
    before_method = text.split("def ensure_model")[0]
    assert "subprocess.run" not in before_method
    assert text.count("subprocess.run") == 1


def test_other_packages_reach_a_model_only_through_the_llm_package():
    for path in outside_llm():
        text = path.read_text(encoding="utf-8")
        assert "redactech.llm.ollama" not in text, path.name
        assert not re.search(r"\bOllamaProvider\b", text), path.name
