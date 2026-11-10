"""Tests of redactech.llm.fake (cassettes) and redactech.llm.none (NoLLM)."""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest
from pydantic import BaseModel

from redactech.config import LLMConfig
from redactech.llm import CassetteMissing, FakeLLM, LLMOutputError, LLMUnavailable, NoLLM
from redactech.llm.fake import cassette_key

CASSETTES = Path(__file__).resolve().parents[1] / "llm_cassettes"
SYSTEM = "You plan changes to technical documentation."


class Plan(BaseModel):
    kind: str
    old: str
    new: str


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """The fake never opens a connection: any attempt fails the test."""

    def refuse(*args, **kwargs):
        raise AssertionError("a network connection was attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)


# --- cassettes ---------------------------------------------------------------------------------


def test_the_key_is_the_sha256_of_system_prompt_and_schema_name():
    expected = hashlib.sha256(("sys" + "prompt" + "Plan").encode("utf-8")).hexdigest()
    assert cassette_key("sys", "prompt", "Plan") == expected
    assert cassette_key("sys", "prompt", "Other") != expected
    assert cassette_key("", "prompt", "Plan") != expected


def test_a_recorded_answer_is_returned():
    llm = FakeLLM(CASSETTES)
    plan = llm.complete_json("Replace LRU1010 by LRU2020", Plan, system=SYSTEM)
    assert plan == Plan(kind="replace_part", old="LRU1010", new="LRU2020")
    assert len(llm.calls) == 1 and llm.calls[0].schema_name == "Plan"


def test_a_cassette_without_system_text_matches_an_empty_system():
    plan = FakeLLM(CASSETTES).complete_json("Delete the step", Plan)  # key from "response"
    assert (plan.kind, plan.old) == ("delete_step", "stp-0003")


def test_successive_answers_serve_the_retries_with_the_error_put_back():
    llm = FakeLLM(CASSETTES)
    plan = llm.complete_json("Replace X2 by X3", Plan, system=SYSTEM)
    assert plan.new == "X3"
    assert [c.attempt for c in llm.calls] == [0, 1, 2]
    # attempt 1 saw the invalid text and the error of attempt 0
    assert llm.calls[1].messages[-2] == {"role": "assistant", "content": "this is not json"}
    assert "was not valid" in llm.calls[1].messages[-1]["content"]
    # attempt 2 saw the missing field named
    assert "new" in llm.calls[2].messages[-1]["content"]


def test_too_few_retries_end_in_an_output_error():
    llm = FakeLLM(CASSETTES, LLMConfig(max_retries=1))
    with pytest.raises(LLMOutputError):
        llm.complete_json("Replace X2 by X3", Plan, system=SYSTEM)
    assert len(llm.calls) == 2


def test_a_request_without_cassette_names_its_key():
    llm = FakeLLM(CASSETTES)
    with pytest.raises(CassetteMissing) as caught:
        llm.complete_json("Unknown request", Plan, system=SYSTEM)
    key = cassette_key(SYSTEM, "Unknown request", "Plan")
    assert caught.value.key == key and key in str(caught.value)
    assert len(llm.calls) == 1  # asked once, no retry on a missing cassette


def test_the_system_text_and_the_schema_are_part_of_the_key():
    llm = FakeLLM(CASSETTES)
    with pytest.raises(CassetteMissing):
        llm.complete_json("Replace LRU1010 by LRU2020", Plan, system="another system")

    class Other(BaseModel):
        kind: str

    with pytest.raises(CassetteMissing):
        llm.complete_json("Replace LRU1010 by LRU2020", Other, system=SYSTEM)


def test_a_missing_cassette_folder_means_no_cassette(tmp_path: Path):
    with pytest.raises(CassetteMissing):
        FakeLLM(tmp_path / "absent").complete_json("p", Plan)


def test_hand_written_cassettes_in_another_folder(tmp_path: Path):
    answer = {"kind": "k", "old": "o", "new": "n"}
    (tmp_path / "one.json").write_text(
        json.dumps({"system": "s", "prompt": "p", "schema": "Plan", "responses": [answer]}),
        encoding="utf-8",
    )
    assert FakeLLM(tmp_path).complete_json("p", Plan, system="s").new == "n"


def test_the_fake_logs_like_any_provider(tmp_path: Path):
    log = tmp_path / "llm_calls.jsonl"
    llm = FakeLLM(CASSETTES, log_path=log)
    llm.complete_json("Replace LRU1010 by LRU2020", Plan, system=SYSTEM)
    (entry,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert entry["provider"] == "fake" and entry["ok"] is True


# --- NoLLM -------------------------------------------------------------------------------------


def test_nollm_is_unavailable_and_does_nothing(tmp_path: Path):
    log = tmp_path / "llm_calls.jsonl"
    llm = NoLLM(log_path=log)
    with pytest.raises(LLMUnavailable, match="no language model"):
        llm.complete_json("p", Plan, system="s", examples=[("q", "a")])
    assert not log.exists()


def test_nollm_refuses_even_a_huge_prompt_as_unavailable():
    with pytest.raises(LLMUnavailable):
        NoLLM().complete_json("x" * 100_000, Plan)
