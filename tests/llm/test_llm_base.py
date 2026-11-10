"""Tests of redactech.llm.base: validation, retries with the error re-injected, token guard, log."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from redactech.config import LLMConfig
from redactech.llm import base
from redactech.llm.base import (
    LLMOutputError,
    LLMProvider,
    LLMUnavailable,
    PromptTooLarge,
    Request,
)

GOOD = '{"kind": "replace_part", "old": "LRU1010", "new": "LRU2020"}'
MISSING = '{"kind": "replace_part", "old": "LRU1010"}'


class Plan(BaseModel):
    kind: str
    old: str
    new: str


class Scripted(LLMProvider):
    """A provider that returns the given raw answers one after the other."""

    name = "scripted"

    def __init__(self, answers, config=None, log_path=None):
        super().__init__(config, log_path)
        self.answers = list(answers)
        self.requests: list[Request] = []

    def _generate(self, request: Request) -> str:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


# --- validation ------------------------------------------------------------------------------


def test_a_valid_answer_is_returned_as_the_model_instance():
    llm = Scripted([GOOD])
    plan = llm.complete_json("Replace LRU1010 by LRU2020", Plan, system="You plan.")
    assert plan == Plan(kind="replace_part", old="LRU1010", new="LRU2020")
    (request,) = llm.requests
    assert request.attempt == 0 and request.schema_name == "Plan"
    assert request.prompt == "Replace LRU1010 by LRU2020" and request.system == "You plan."


def test_the_json_schema_is_given_to_the_provider():
    llm = Scripted([GOOD])
    llm.complete_json("p", Plan)
    assert llm.requests[0].schema_json == Plan.model_json_schema()
    assert set(llm.requests[0].schema_json["required"]) == {"kind", "old", "new"}


def test_the_temperature_and_the_model_come_from_the_config():
    llm = Scripted([GOOD], LLMConfig(temperature=0.3, model="some-model:1b"))
    llm.complete_json("p", Plan)
    assert (llm.requests[0].temperature, llm.requests[0].model) == (0.3, "some-model:1b")
    default = Scripted([GOOD])
    default.complete_json("p", Plan)
    assert default.requests[0].temperature == 0.0  # the default configuration


@pytest.mark.parametrize(
    "answer", ["not json at all", "[1, 2]", '{"kind": 1, "old": "a", "new": "b"}', MISSING, ""]
)
def test_an_answer_that_does_not_fit_the_schema_is_refused(answer: str):
    llm = Scripted([answer, GOOD])
    assert llm.complete_json("p", Plan).new == "LRU2020"
    assert len(llm.requests) == 2  # refused once, then asked again


# --- retries with the error re-injected ----------------------------------------------------------


def test_the_validation_error_is_put_back_in_the_conversation():
    llm = Scripted([MISSING, GOOD])
    plan = llm.complete_json("Replace it", Plan, system="You plan.")
    assert plan.new == "LRU2020"
    first, second = llm.requests
    assert (first.attempt, second.attempt) == (0, 1)
    assert len(second.messages) == len(first.messages) + 2
    answer, request = second.messages[-2:]
    assert answer == {"role": "assistant", "content": MISSING}
    assert request["role"] == "user" and "was not valid" in request["content"]
    assert "new" in request["content"]  # the missing field is named in the error
    assert second.messages[:-2] == first.messages  # nothing else changed
    assert second.prompt == first.prompt == "Replace it"


def test_retries_are_bounded_by_the_configuration():
    for retries, attempts in [(0, 1), (1, 2), (2, 3), (5, 6)]:
        llm = Scripted(["bad"] * 10, LLMConfig(max_retries=retries))
        with pytest.raises(LLMOutputError, match=f"{attempts} attempt"):
            llm.complete_json("p", Plan)
        assert len(llm.requests) == attempts


def test_the_default_is_two_retries():
    llm = Scripted(["bad"] * 10)
    with pytest.raises(LLMOutputError):
        llm.complete_json("p", Plan)
    assert len(llm.requests) == 3


def test_a_provider_error_is_not_retried():
    llm = Scripted([LLMUnavailable("down"), GOOD])
    with pytest.raises(LLMUnavailable):
        llm.complete_json("p", Plan)
    assert len(llm.requests) == 1


# --- conversation --------------------------------------------------------------------------------


def test_the_system_text_the_examples_and_the_prompt_make_the_conversation():
    llm = Scripted([GOOD])
    examples = [
        ("Replace A by B", Plan(kind="replace_part", old="A", new="B")),
        ("Replace C by D", {"kind": "replace_part", "old": "C", "new": "D"}),
        ("Replace E by F", '{"kind": "replace_part", "old": "E", "new": "F"}'),
    ]
    llm.complete_json("Replace G by H", Plan, system="You plan.", examples=examples)
    messages = llm.requests[0].messages
    assert [m["role"] for m in messages] == [
        "system", "user", "assistant", "user", "assistant", "user", "assistant", "user"]
    assert messages[0]["content"].startswith("You plan.") and "JSON" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "Replace G by H"}
    for turn in (2, 4, 6):  # every example answer is JSON that fits the schema
        Plan.model_validate_json(messages[turn]["content"])


def test_without_a_system_text_the_json_instruction_is_still_there():
    llm = Scripted([GOOD])
    llm.complete_json("p", Plan)
    assert llm.requests[0].messages[0]["role"] == "system"
    assert llm.requests[0].messages[0]["content"] == base.JSON_ONLY


# --- token guard ---------------------------------------------------------------------------------


def test_the_token_estimate_is_one_per_four_characters():
    assert base.estimate_tokens("") == 0 and base.estimate_tokens("abcd") == 1
    assert base.estimate_tokens("abcde") == 2 and base.estimate_tokens("ab", "cd") == 1


def test_a_prompt_of_six_thousand_tokens_is_refused_before_any_call():
    llm = Scripted([GOOD])
    with pytest.raises(PromptTooLarge, match="6000"):
        llm.complete_json("x" * 24_000, Plan)
    assert llm.requests == []  # nothing was sent


def test_a_small_prompt_passes_and_the_system_text_and_examples_count():
    assert Scripted([GOOD]).complete_json("x" * 4_000, Plan).kind == "replace_part"
    with pytest.raises(PromptTooLarge):
        Scripted([GOOD]).complete_json("p", Plan, system="s" * 24_000)
    with pytest.raises(PromptTooLarge):
        Scripted([GOOD]).complete_json("p", Plan, examples=[("e" * 24_000, GOOD)])


# --- local log --


def read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_every_attempt_is_logged_without_the_prompt(tmp_path: Path):
    log = tmp_path / "runs" / "r1" / "llm_calls.jsonl"
    llm = Scripted([MISSING, GOOD], LLMConfig(model="m:1b"), log_path=log)
    llm.complete_json("SECRET-LOOKING PROMPT TEXT", Plan, system="private system")
    first, second = read_log(log)
    assert (first["ok"], second["ok"]) == (False, True)
    assert first["error"] and second["error"] is None
    assert (first["attempt"], second["attempt"]) == (0, 1)
    assert (first["provider"], first["model"], first["schema"]) == ("scripted", "m:1b", "Plan")
    assert len(first["prompt_sha256"]) == 64 and first["prompt_sha256"] != second["prompt_sha256"]
    assert first["duration_s"] >= 0 and first["time"]
    text = log.read_text(encoding="utf-8")
    assert "SECRET-LOOKING" not in text and "private system" not in text and "LRU1010" not in text


def test_the_hash_identifies_the_conversation(tmp_path: Path):
    log = tmp_path / "calls.jsonl"
    Scripted([GOOD, GOOD], log_path=log).complete_json("same prompt", Plan)
    Scripted([GOOD], log_path=log).complete_json("same prompt", Plan)
    Scripted([GOOD], log_path=log).complete_json("other prompt", Plan)
    hashes = [entry["prompt_sha256"] for entry in read_log(log)]
    assert hashes[0] == hashes[1] != hashes[2]  # appended, never overwritten


def test_an_error_of_the_provider_is_logged(tmp_path: Path):
    log = tmp_path / "calls.jsonl"
    llm = Scripted([LLMUnavailable("down")], log_path=log)
    with pytest.raises(LLMUnavailable):
        llm.complete_json("p", Plan)
    (entry,) = read_log(log)
    assert entry["ok"] is False and entry["error"].startswith("LLMUnavailable: down")


def test_no_log_file_without_a_log_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Scripted([GOOD]).complete_json("p", Plan)
    assert list(tmp_path.iterdir()) == []


def test_prompt_hash_is_stable_and_order_independent_of_keys():
    a = [{"role": "user", "content": "x"}]
    b = [{"content": "x", "role": "user"}]
    assert base.prompt_hash(a) == base.prompt_hash(b) != base.prompt_hash([])
