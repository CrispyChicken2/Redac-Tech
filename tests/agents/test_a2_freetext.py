"""Tests of redactech.agents.a2_freetext: the model proposes, the code checks every operation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redactech.agents import a2_freetext as ft
from redactech.agents import a4_locator
from redactech.agents.a2_mapping import REQUIRED
from redactech.config import LLMConfig
from redactech.llm import FakeLLM, LLMUnavailable, NoLLM, PromptTooLarge
from redactech.llm.base import LLMProvider, Request
from redactech.s1000d import index as ix
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CASSETTES = Path(__file__).resolve().parents[1] / "llm_cassettes"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
FR = "Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation."
EN = "Replace part LRU1010 with LRU2020 throughout the documentation."


class Scripted(LLMProvider):
    """A model that answers with a given JSON object (or text), and records what it was asked."""

    name = "scripted"

    def __init__(self, answer):
        super().__init__(LLMConfig(max_retries=0))
        self.answer = answer
        self.requests: list[Request] = []

    def _generate(self, request: Request) -> str:
        self.requests.append(request)
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


def op(kind: str, params: dict, quotes: list[str], **extra) -> dict:
    return {"kind": kind, "params": params, "quotes": quotes, **extra}


def response(*operations: dict, questions=()) -> dict:
    return {"operations": list(operations), "questions": list(questions)}


@pytest.fixture(scope="module")
def index() -> ix.CorpusIndex:
    folder = FIXTURES.resolve()
    source = wsmod.Source("fixtures", folder, [folder], "4.1")
    return ix.build_index(wsmod.Workspace([source], folder))


def run(text: str, answer, index) -> ft.Interpretation:
    return ft.interpret_full(text, index, Scripted(answer))


# --- operations that pass ------------------------------------------------------------------------


def test_a_clear_request_gives_one_operation_with_its_source(index):
    answer = response(op("replace_part", {"old": "LRU1010", "new": "LRU2020"},
                         ["LRU1010 par LRU2020"], reason="Remplacement"))
    result = run(FR, answer, index)
    assert result.questions == []
    (operation,) = result.operations
    assert (operation.id, operation.kind) == ("op-0001", "replace_part")
    assert operation.params == {"old": "LRU1010", "new": "LRU2020"}
    assert operation.rationale == "Remplacement" and operation.target.ref is None
    (span,) = operation.source
    assert span.doc == "free_text" and span.quote == "LRU1010 par LRU2020"
    assert FR[span.start:span.end] == span.quote  # the offsets point at the quote


def test_the_operations_are_ordinary_operations_for_the_pipeline(index):
    answer = response(op("replace_part", {"old": "LRU1010", "new": "LRU2020"}, ["LRU1010"]))
    (operation,) = ft.interpret(FR, index, Scripted(answer))
    zones = a4_locator.locate(operation, index).zones
    assert len(zones) >= 3  # the same occurrences as a mapping table finds


def test_the_recorded_answers_give_the_same_operation_in_french_and_english(index):
    llm = FakeLLM(CASSETTES)
    fr = ft.interpret(FR, index, llm)
    en = ft.interpret(EN, index, llm)
    expected = [{"old": "LRU1010", "new": "LRU2020"}]
    assert [o.params for o in fr] == [o.params for o in en] == expected
    assert fr[0].source[0].quote == "LRU1010 par LRU2020"
    assert en[0].source[0].quote == "LRU1010 with LRU2020"


def test_a_step_operation_names_its_document_in_several_ways(index):
    text = "Insert the step 'Wear gloves.' after stp-0002 in the replace-the-bracket procedure"
    for name in (PROCED, PROCED.removesuffix(".XML"), PROCED.lower(),
                 f"fixtures:{PROCED.removesuffix('.XML')}"):
        answer = response(op("insert_step", {"para": "Wear gloves.", "after_id": "stp-0002"},
                             ["Insert the step 'Wear gloves.' after stp-0002"],
                             target_doc=name, target_id="stp-0002"))
        (operation,) = ft.interpret(text, index, Scripted(answer))
        assert operation.target.ref.doc_key == PROCED.removesuffix(".XML")
        assert operation.target.element_id == "stp-0002"


def test_several_operations_are_numbered_among_the_accepted_ones(index):
    text = "Replace LRU1010 with LRU2020. Replace X2 with X3. Replace ZZZ with YYY."
    answer = response(
        op("replace_part", {"old": "LRU1010", "new": "LRU2020"}, ["Replace LRU1010 with LRU2020"]),
        op("replace_part", {"old": "ZZZ", "new": "YYY"}, ["Replace ZZZ with YYY"]),  # unknown
        op("replace_part", {"old": "X2", "new": "X3"}, ["Replace X2 with X3"]),
    )
    result = run(text, answer, index)
    assert [o.id for o in result.operations] == ["op-0001", "op-0002"]
    assert [o.params["old"] for o in result.operations] == ["LRU1010", "X2"]
    assert len(result.questions) == 1 and "'ZZZ'" in result.questions[0]


def test_unknown_parameters_are_dropped_and_the_keyword_of_a_requirement_is_allowed(index):
    text = "Add a spare FAKE-PN-077 from FAKE1, quantity 2, to the bracket procedure"
    answer = response(op(
        "add_requirement",
        {"requirement": "spare", "part_number": "FAKE-PN-077", "manufacturer_code": "FAKE1",
         "quantity": "2", "colour": "red"},
        ["Add a spare FAKE-PN-077 from FAKE1, quantity 2"], target_doc=PROCED))
    (operation,) = ft.interpret(text, index, Scripted(answer))
    assert "colour" not in operation.params and operation.params["requirement"] == "spare"


# --- operations that become questions -----------------------------------------------------------


def test_a_value_that_is_not_in_the_request_is_never_accepted(index):
    request = "Replace the part LRU1010 by its successor."
    answer = response(op("replace_part", {"old": "LRU1010", "new": "LRU9999"},
                         ["Replace the part LRU1010"]))
    result = run(request, answer, index)
    assert result.operations == []
    (question,) = result.questions
    assert "LRU9999" in question and "not in your request" in question


def test_the_recorded_trap_is_caught(index):
    request = "Replace the part LRU1010 by its successor."
    result = ft.interpret_full(request, index, FakeLLM(CASSETTES))
    assert result.operations == [] and "LRU9999" in result.questions[0]


def test_a_single_word_value_must_be_a_whole_word(index):
    text = "Add the spare FAKE-PN-077 from FAKE1, quantity LRU2020, to the bracket procedure"
    params = {"requirement": "spare", "part_number": "FAKE-PN-077", "manufacturer_code": "FAKE1",
              "quantity": "2"}
    answer = response(op("add_requirement", params, ["Add the spare FAKE-PN-077 from FAKE1"],
                         target_doc=PROCED))
    result = run(text, answer, index)  # "2" is only inside "LRU2020"
    assert result.operations == [] and "'2'" in result.questions[0]
    ok = run(text.replace("LRU2020", "2"), answer, index)
    assert len(ok.operations) == 1


def test_a_quote_that_is_not_in_the_request_drops_the_operation(index):
    answer = response(op("replace_part", {"old": "LRU1010", "new": "LRU2020"},
                         ["LRU1010 devient LRU2020"]))
    result = run(FR, answer, index)
    assert result.operations == []
    assert "not in your request" in result.questions[0] and "devient" in result.questions[0]


def test_an_operation_without_quotes_is_refused(index):
    answer = response(op("replace_part", {"old": "LRU1010", "new": "LRU2020"}, []))
    result = run(FR, answer, index)
    assert result.operations == [] and "no quote" in result.questions[0]
    blank = response(op("replace_part", {"old": "LRU1010", "new": "LRU2020"}, ["  "]))
    assert run(FR, blank, index).operations == []


def test_a_value_to_replace_that_does_not_exist_is_a_question(index):
    text = "Remplacer la pièce ABC123 par LRU2020"
    params = {"old": "ABC123", "new": "LRU2020"}
    answer = response(op("replace_part", params, ["ABC123 par LRU2020"]))
    result = run(text, answer, index)
    assert result.operations == [] and "'ABC123' was not found" in result.questions[0]


def test_a_text_to_replace_must_exist_in_the_documentation(index):
    text = "In the bracket procedure, replace 'by hand' with 'with a wrench'"
    good = response(op("replace_text", {"old": "by hand", "new": "with a wrench"},
                       ["replace 'by hand' with 'with a wrench'"], target_doc=PROCED,
                       target_id="stp-0003"))
    # "stp-0003" is not written in the request: the id is a value too
    result = run(text, good, index)
    assert result.operations == [] and "stp-0003" in result.questions[0]
    text = "In step stp-0003 of the bracket procedure, replace 'by hand' with 'with a wrench'"
    (operation,) = ft.interpret(text, index, Scripted(good))
    assert operation.target.element_id == "stp-0003"
    missing = response(op("replace_text", {"old": "never written anywhere", "new": "x"},
                          ["replace 'by hand' with 'with a wrench'"], target_doc=PROCED))
    assert run(text + " never written anywhere x", missing, index).operations == []


def test_the_target_document_must_be_known(index):
    text = "Delete step stp-0003 of the brake manual"
    for target in (None, "brake manual", "DMC-NOPE-AAA.XML"):
        answer = response(op("delete_step", {"step_id": "stp-0003"},
                             ["Delete step stp-0003"], target_doc=target))
        result = run(text, answer, index)
        assert result.operations == [] and "Which document" in result.questions[0]


def test_a_missing_required_parameter_is_a_question(index):
    text = "Insert a step 'Wear gloves.' in the bracket procedure"
    answer = response(op("insert_step", {"para": "Wear gloves."},
                         ["Insert a step 'Wear gloves.'"], target_doc=PROCED))
    result = run(text, answer, index)  # neither after_id nor before_id
    assert result.operations == [] and "after_id or before_id" in result.questions[0]


def test_the_questions_of_the_model_are_passed_on(index):
    answer = response(questions=["Quelle pièce remplace LRU1010 ?", "  ", ""])
    result = run("Remplacer LRU1010", answer, index)
    assert result.operations == [] and result.questions == ["Quelle pièce remplace LRU1010 ?"]


def test_an_empty_request_asks_nothing_of_the_model(index):
    llm = Scripted(response())
    result = ft.interpret_full("   ", index, llm)
    assert result.operations == [] and result.questions == ["The request is empty."]
    assert llm.requests == []


# --- the prompt and the failures of the model ------------------------------------------------


def test_the_prompt_holds_the_request_the_documents_and_the_part_numbers(index):
    llm = Scripted(response())
    ft.interpret_full(FR, index, llm)
    (request,) = llm.requests
    assert request.schema_name == "OpsResponse"
    assert FR in request.prompt and PROCED in request.prompt
    assert "LRU1010" in request.prompt and "FAKE-PN-001" in request.prompt
    assert request.system == ft.system_prompt()
    assert set(request.schema_json["properties"]) == {"operations", "questions"}


def test_the_system_prompt_lists_every_operation_kind_with_its_parameters():
    text = ft.system_prompt()
    for kind, needs in REQUIRED.items():
        assert f"- {kind}:" in text, kind
        for need in needs:
            for name in (need if isinstance(need, tuple) else (need,)):
                assert name in text, (kind, name)
    assert "character for character" in text and "Never invent" in text


def test_the_prompt_stays_small_even_with_many_part_numbers(index):
    prompt = ft.build_prompt(FR, index)
    assert len(prompt) < 12_000
    assert prompt.count("\n- ") <= ft.MAX_DOCS


def test_without_a_model_the_request_is_unavailable(index):
    with pytest.raises(LLMUnavailable):
        ft.interpret(FR, index, NoLLM())


def test_a_huge_request_is_refused_before_the_call(index):
    llm = Scripted(response())
    with pytest.raises(PromptTooLarge):
        ft.interpret("x " * 20_000, index, llm)
    assert llm.requests == []


def test_an_answer_that_is_not_the_schema_is_a_failure_of_the_model(index):
    from redactech.llm import LLMOutputError

    with pytest.raises(LLMOutputError):
        ft.interpret(FR, index, Scripted({"operations": [{"kind": "launch_rocket"}]}))
