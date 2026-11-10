"""Tests of redactech.llm.ollama with a mock transport: no server, no network, no download."""

from __future__ import annotations

import json
import subprocess

import httpx
import pytest
from pydantic import BaseModel

from redactech.config import LLMConfig
from redactech.llm import LLMOutputError, LLMUnavailable, RemoteLLMRefused
from redactech.llm import ollama as ollama_module
from redactech.llm.ollama import ALLOW_REMOTE_ENV, OllamaProvider, check_host

GOOD = {"kind": "replace_part", "old": "A", "new": "B"}


class Plan(BaseModel):
    kind: str
    old: str
    new: str


@pytest.fixture(autouse=True)
def local_only(monkeypatch):
    monkeypatch.delenv(ALLOW_REMOTE_ENV, raising=False)


def provider(handler, config=None, base_url="http://localhost:11434"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider(config, base_url=base_url, client=client)


def answer(content) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"message": {"role": "assistant", "content": text}})


# --- the request ---------------------------------------------------------------------------------


def test_the_chat_request_carries_the_schema_the_model_and_the_temperature():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(GOOD)

    llm = provider(handler, LLMConfig(model="ministral-3:8b", temperature=0))
    plan = llm.complete_json("Replace A by B", Plan, system="You plan.")
    assert plan == Plan(**GOOD)
    (request,) = seen
    assert request.method == "POST" and str(request.url) == "http://localhost:11434/api/chat"
    body = json.loads(request.content)
    assert body["model"] == "ministral-3:8b" and body["stream"] is False
    assert body["format"] == Plan.model_json_schema()
    assert body["options"] == {"temperature": 0}
    assert body["messages"][-1] == {"role": "user", "content": "Replace A by B"}
    assert body["messages"][0]["role"] == "system"


def test_the_model_is_one_config_line():
    models = []

    def handler(request: httpx.Request) -> httpx.Response:
        models.append(json.loads(request.content)["model"])
        return answer(GOOD)

    for name in ("model-a:1b", "model-b:7b"):
        provider(handler, LLMConfig(model=name)).complete_json("p", Plan)
    assert models == ["model-a:1b", "model-b:7b"]


def test_an_invalid_answer_is_asked_again_with_the_error():
    bodies = []
    answers = ["oops", {"kind": "k", "old": "o"}, GOOD]

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return answer(answers[len(bodies) - 1])

    plan = provider(handler).complete_json("p", Plan)
    assert plan.new == "B" and len(bodies) == 3
    assert bodies[1]["messages"][-2] == {"role": "assistant", "content": "oops"}
    assert "was not valid" in bodies[1]["messages"][-1]["content"]
    assert "new" in bodies[2]["messages"][-1]["content"]


def test_endless_invalid_answers_stop_after_the_configured_retries():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return answer("never json")

    with pytest.raises(LLMOutputError):
        provider(handler, LLMConfig(max_retries=1)).complete_json("p", Plan)
    assert len(calls) == 2


# --- the server is missing or broken ------------------------------------------------------------


def test_a_server_that_does_not_answer_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailable, match="does not answer"):
        provider(handler).complete_json("p", Plan)


def test_an_http_error_and_a_strange_payload_are_unavailable_without_retry():
    calls = []

    def failing(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="boom")

    with pytest.raises(LLMUnavailable, match="HTTP 500"):
        provider(failing).complete_json("p", Plan)
    assert len(calls) == 1

    def strange(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(LLMUnavailable, match="unexpected"):
        provider(strange).complete_json("p", Plan)


def test_a_large_prompt_is_refused_before_the_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return answer(GOOD)

    from redactech.llm import PromptTooLarge

    with pytest.raises(PromptTooLarge):
        provider(handler).complete_json("x" * 30_000, Plan)
    assert calls == []


# --- the host guard -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434/"]
)
def test_this_machine_is_allowed(url: str):
    assert check_host(url) == url.rstrip("/")
    assert OllamaProvider(base_url=url).base_url == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org:11434",
        "http://192.168.1.20:11434",
        "http://10.0.0.5",
        "https://api.example.com",
        "http://localhost.evil.example:11434",
        "http://127.0.0.1.evil.example",
        "http://user@evil.example/",
        "not a url",
    ],
)
def test_any_other_host_is_refused(url: str):
    with pytest.raises(RemoteLLMRefused):
        OllamaProvider(base_url=url)


def test_remote_use_needs_the_explicit_environment_variable(monkeypatch):
    url = "http://gpu-box.example:11434"
    monkeypatch.setenv(ALLOW_REMOTE_ENV, "0")
    with pytest.raises(RemoteLLMRefused):
        check_host(url)
    monkeypatch.setenv(ALLOW_REMOTE_ENV, "true")
    with pytest.raises(RemoteLLMRefused):
        check_host(url)
    monkeypatch.setenv(ALLOW_REMOTE_ENV, "1")
    assert check_host(url) == url
    assert OllamaProvider(base_url=url).base_url == url


def test_the_guard_is_checked_again_when_the_request_is_made(monkeypatch):
    llm = provider(lambda request: answer(GOOD))
    llm.base_url = "http://evil.example:11434"  # changed after construction
    with pytest.raises(RemoteLLMRefused):
        llm.complete_json("p", Plan)


# --- ensure_model: one pull, only on request ------------------------------------------------------


def tags(*names: str):
    return lambda request: httpx.Response(200, json={"models": [{"name": n} for n in names]})


def test_building_the_provider_pulls_and_requests_nothing(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("nothing must run when the provider is built")

    monkeypatch.setattr(subprocess, "run", forbidden)
    calls = []
    llm = provider(lambda request: calls.append(request) or answer(GOOD))
    assert llm.base_url == "http://localhost:11434" and calls == []


def test_a_model_that_is_there_is_not_pulled(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no pull expected"))
    llm = provider(tags("ministral-3:8b"), LLMConfig(model="ministral-3:8b"))
    assert llm.has_model() and llm.ensure_model()


def test_a_missing_model_is_pulled_once_even_if_it_fails(monkeypatch):
    runs = []

    def fake_run(command, **kwargs):
        runs.append(command)
        return subprocess.CompletedProcess(command, 1, b"", b"error")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(ollama_module.shutil, "which", lambda name: "/usr/bin/ollama")
    llm = provider(tags("other-model:1b"), LLMConfig(model="ministral-3:8b"))
    assert llm.ensure_model() is False and llm.ensure_model() is False
    assert runs == [["ollama", "pull", "ministral-3:8b"]]  # tried once, never again


def test_a_successful_pull_makes_the_model_available(monkeypatch):
    state = {"pulled": False}

    def handler(request: httpx.Request) -> httpx.Response:
        names = ["ministral-3:8b"] if state["pulled"] else []
        return httpx.Response(200, json={"models": [{"name": n} for n in names]})

    def fake_run(command, **kwargs):
        state["pulled"] = True
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(ollama_module.shutil, "which", lambda name: "/usr/bin/ollama")
    assert provider(handler, LLMConfig(model="ministral-3:8b")).ensure_model() is True


def test_without_the_ollama_program_nothing_is_run(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("not installed"))
    monkeypatch.setattr(ollama_module.shutil, "which", lambda name: None)
    assert provider(tags()).ensure_model() is False


def test_a_server_that_cannot_list_models_has_no_model():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert provider(handler).has_model() is False


# --- the real local model (skipped unless REDACTECH_OLLAMA=1) --


class Number(BaseModel):
    value: int


@pytest.mark.ollama
def test_the_real_local_model_answers_a_tiny_schema():
    llm = OllamaProvider()  # http://localhost:11434, [llm] defaults
    assert llm.ensure_model()
    result = llm.complete_json("Give the number 3 as value.", Number, system="Answer in JSON.")
    assert isinstance(result, Number) and result.value == 3
