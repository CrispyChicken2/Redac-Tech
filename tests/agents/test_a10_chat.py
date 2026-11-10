"""Tests of redactech.agents.a10_chat: a request in the chat becomes operations, through A0."""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

import pytest

from redactech.agents import a10_chat as chat
from redactech.llm import FakeLLM, NoLLM
from redactech.pipeline import orchestrator as orch
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CASSETTES = Path(__file__).resolve().parents[1] / "llm_cassettes"
CODE = "AAA-D00-00-00-00AA"
FILES = (
    f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML",
    f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML",
    f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML",
    f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML",
    f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML",
)
NOW = datetime.datetime(2025, 3, 7, 14, 5, 9)
FR = "Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation."
EN = "Replace part LRU1010 with LRU2020 throughout the documentation."
TRAP = "Replace the part LRU1010 by its successor."


@pytest.fixture
def run(tmp_path: Path) -> orch.Run:
    """A run under review: X2 replaced by X3 (the writer's first request), nothing decided."""
    src = tmp_path / "src"
    src.mkdir()
    for name in FILES:
        shutil.copy(FIXTURES / name, src / name)
    folder = src.resolve()
    source = wsmod.Source("fixtures", folder, [folder], "4.1")
    ws = wsmod.save_workspace(wsmod.Workspace([source], tmp_path), tmp_path / "ws.toml")
    form = {"kind": "replace_part", "old": "X2", "new": "X3"}
    started = orch.start(orch.RunRequest(form=form), ws, tmp_path / "runs",
                         clock=lambda: NOW, token="ch01")
    started.set_policy(started.suggestion().model_copy(update={"mode": "in_work"}))
    started.run_to_review()
    return started


# --- a request becomes operations added to the run ---------------------------------------


def test_a_request_in_french_adds_the_operation_and_its_proposals(run: orch.Run):
    before = len(run.state.proposals)
    pending_before = len(run.pending_ids())
    reply = chat.answer(FR, run, FakeLLM(CASSETTES))
    (added,) = reply.operations_added
    assert (added.id, added.kind) == ("op-0002", "replace_part")
    assert added.params == {"old": "LRU1010", "new": "LRU2020"}
    assert added.rationale == 'Free-text request: "LRU1010 par LRU2020"'
    assert reply.text.startswith("1 opération(s) ajoutée(s), 3 proposition(s) à décider")
    assert len(run.state.proposals) > before and len(run.pending_ids()) == pending_before + 3
    assert [o.id for o in run.base_operations()] == ["op-0001", "op-0002"]


def test_the_same_request_in_english(run: orch.Run):
    reply = chat.answer(EN, run, FakeLLM(CASSETTES))
    assert reply.text.startswith("1 operation(s) added, 3 proposal(s) to decide.")
    assert [o.params["new"] for o in reply.operations_added] == ["LRU2020"]


def test_the_new_proposals_still_need_the_decisions_of_the_writer(run: orch.Run):
    reply = chat.answer(EN, run, FakeLLM(CASSETTES))
    new = [p for p in run.state.proposals if p.operation_id == "op-0002"]
    assert len(new) >= 3 and {p.status for p in new} == {"proposed"}  # nothing accepted by the chat
    assert sorted(reply.sources) == sorted(p.id for p in new)
    assert run.state.stage == "proposals_ready"
    assert not (run.run_dir / "out").exists()  # nothing written


def test_earlier_decisions_are_kept(run: orch.Run):
    first = run.pending_ids()[0]
    run.decide(first, "accepted")
    chat.answer(EN, run, FakeLLM(CASSETTES))
    assert next(p.status for p in run.state.proposals if p.id == first) == "accepted"
    assert first not in run.pending_ids()


def test_an_invented_value_gives_a_question_and_adds_nothing(run: orch.Run):
    before = len(run.state.proposals)
    reply = chat.answer(TRAP, run, FakeLLM(CASSETTES))
    assert reply.operations_added == [] and len(run.state.proposals) == before
    assert reply.text.splitlines()[0] == "No operation could be kept."
    lines = reply.text.splitlines()
    assert any("LRU9999" in line and line.startswith("- Question") for line in lines)
    assert any("LRU9999" in q for q in run.free_text_questions())  # also for the customer questions
    assert not any("LRU9999" in str(p.after_xml) for p in run.state.proposals)


def test_the_model_calls_of_the_chat_are_logged_in_the_run_folder(run: orch.Run):
    llm = FakeLLM(CASSETTES)
    chat.answer(EN, run, llm)
    assert (run.run_dir / "llm_calls.jsonl").is_file() and llm.log_path is None


def test_without_a_model_a_request_is_not_read(run: orch.Run):
    for provider in (None, NoLLM()):
        reply = chat.answer(FR, run, provider)
        assert "modèle local" in reply.text and reply.operations_added == []
    assert [o.id for o in run.base_operations()] == ["op-0001"]


def test_a_request_the_model_does_not_know_is_a_message_not_a_crash(run: orch.Run):
    reply = chat.answer("A request nobody recorded", run, FakeLLM(CASSETTES))
    assert reply.operations_added == [] and "model could not read" in reply.text


def test_after_the_write_the_decisions_are_closed(run: orch.Run):
    for proposal_id in run.pending_ids():
        run.decide(proposal_id, "accepted")
    run.write(today=datetime.date(2025, 3, 7))
    reply = chat.answer(EN, run, FakeLLM(CASSETTES))
    assert reply.text == "Decisions are closed: the run is already written."
    assert reply.operations_added == []


def test_a_question_does_not_reach_the_model_as_a_request(run: orch.Run):
    plain = chat.answer("Show me the errors", run, None)
    assert plain.text.startswith("Introduced errors (0):")
    llm = FakeLLM(CASSETTES)
    assert chat.answer("Show me the errors", run, llm).text == plain.text
    # at most a rephrasing was asked (no cassette: the code list stays); never a request reading
    assert {call.schema_name for call in llm.calls} <= {"Rephrased"}
    assert [o.id for o in run.base_operations()] == ["op-0001"]
