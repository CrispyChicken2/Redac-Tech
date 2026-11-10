"""Tests of redactech.agents.a10_chat (status replies): built by code from the run state."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from redactech.agents import a10_chat as chat
from redactech.llm import NoLLM
from redactech.llm.base import LLMProvider, LLMUnavailable, Request

A = "DMC-A-520A-A_001-00_EN-US.XML"
B = "DMC-B-0A3A-D_001-00_EN-US.XML"
QUESTION = "The request 'add a note' conflicts with business rule R-1: No <note> here. Proceed?"


class Scripted(LLMProvider):
    """A model that returns a given text, and records what it was asked."""

    name = "scripted"

    def __init__(self, make):
        super().__init__()
        self.make = make
        self.requests: list[Request] = []

    def _generate(self, request: Request) -> str:
        self.requests.append(request)
        prompt = request.prompt
        listing = prompt[prompt.index("\n\n") + 2:]
        return json.dumps({"text": self.make(listing)})


@pytest.fixture
def run(state, index, tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(state=state, index=index, run_dir=tmp_path)


def lines_of(reply: chat.ChatReply) -> list[str]:
    return reply.text.splitlines()


# --- classification -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "kind", "sections"),
    [
        ("Fais-moi un récap des erreurs et des points en attente", "status",
         ["errors", "pending"]),
        ("recap", "status", ["changes", "errors", "pending", "blocked"]),
        ("Donne-moi un résumé", "status", ["changes", "errors", "pending", "blocked"]),
        ("Show me the errors", "status", ["errors"]),
        ("How many errors are there?", "status", ["errors"]),
        ("What is pending?", "status", ["pending"]),
        ("Quelles demandes sont bloquées ?", "status", ["blocked"]),
        ("Which requests are blocked?", "status", ["blocked"]),
        ("Summary of changed parts and pending items", "status", ["changes", "pending"]),
        ("Liste des pièces modifiées", "status", ["changes"]),
        ("Remplacer la pièce LRU1010 par LRU2020", "request", []),
        ("Replace part A with B because of the errors in the manual", "request", []),
        ("Delete step stp-0003 of the bracket procedure", "request", []),
        ("Supprimer l'étape stp-0003", "request", []),
        ("Ajouter un tool FAKE-PN-077", "request", []),
        ("Bonjour", "request", []),
    ],
)
def test_the_message_is_a_question_about_the_run_or_a_request(message, kind, sections):
    assert chat.classify(message) == (kind, sections)


def test_the_language_of_the_reply_follows_the_message():
    assert chat.language("Fais-moi un récap des erreurs") == "fr"
    assert chat.language("Quelles sont les demandes bloquées ?") == "fr"
    assert chat.language("Show me the errors and the pending items") == "en"
    assert chat.language("recap") == "en"


# --- the sections, built by code -----------------------------------------------------------------


def test_the_errors_are_the_introduced_and_the_pre_existing_ones(run):
    reply = chat.answer("Show me the errors", run)
    assert lines_of(reply) == [
        "Introduced errors (1):",
        f"- {A}: brex: forbidden <value>",
        "Pre-existing errors (1):",
        f"- {A}: xsd: old problem",
    ]
    assert reply.operations_added == []


def test_the_pending_items_come_with_the_comment_of_the_writer(run):
    reply = chat.answer("What is pending?", run)
    assert lines_of(reply) == ["Pending for the customer (1):", f"- {B}: Ask the customer <b>?</b>"]
    assert reply.sources == ["p2"]


def test_the_blocked_requests_come_with_the_rule_and_the_question(run):
    reply = chat.answer("What is blocked?", run)
    assert lines_of(reply) == [
        "Blocked by a rule (1):",
        f"- {A}: R-1: No <note> here.: {QUESTION}",
    ]
    assert reply.sources == ["p4"]


def test_the_changed_parts_are_listed_per_document_without_the_rejected_ones(run):
    reply = chat.answer("Changed parts, please", run)
    assert lines_of(reply) == [
        "Changed parts (3):",
        f"- {A}: replace_part (accepted)",
        f"- {B}: replace_part (pending_client)",
        f"- {B}: replace_text (edited)",
    ]
    assert "p5" not in reply.sources  # rejected: not a change


def test_a_recap_without_a_topic_has_every_section_in_order(run):
    reply = chat.answer("recap", run)
    titles = [line for line in lines_of(reply) if not line.startswith("- ")]
    assert titles == [
        "Changed parts (3):", "Introduced errors (1):", "Pre-existing errors (1):",
        "Pending for the customer (1):", "Blocked by a rule (1):",
    ]


def test_a_french_message_gets_a_french_reply(run):
    reply = chat.answer("Fais-moi un récap des erreurs et des points en attente", run)
    assert lines_of(reply) == [
        "Erreurs introduites (1):",
        f"- {A}: brex: forbidden <value>",
        "Erreurs préexistantes (1):",
        f"- {A}: xsd: old problem",
        "En attente du client (1):",
        f"- {B}: Ask the customer <b>?</b>",
    ]


def test_an_empty_section_says_none(run):
    run.state.proposals = []
    reply = chat.answer("What is pending?", run)
    assert lines_of(reply) == ["Pending for the customer (0):", "- none"]
    assert lines_of(chat.answer("Quelles demandes sont bloquées ?", run)) == [
        "Bloquées par une règle (0):", "- aucune"]


def test_nothing_is_added_to_what_the_code_found(run):
    """Every bullet of a reply is a fact of the run; the figures in the titles are the counts."""
    reply = chat.answer("recap", run)
    bullets = [line for line in lines_of(reply) if line.startswith("- ")]
    assert len(bullets) == 3 + 1 + 1 + 1 + 1
    assert all(A in b or B in b for b in bullets)


def test_without_a_run_or_a_message_the_reply_says_so(run):
    assert chat.answer("recap", None).text == "No run in progress."
    assert chat.answer("récap", None).text == "Aucun run en cours."
    assert chat.answer("   ", run).text == "Ask a question or describe a change."


# --- the model may rephrase, never add --------------------------------------


def test_without_a_model_the_code_list_is_returned_as_it_is(run):
    plain = chat.answer("Show me the errors", run).text
    for provider in (None, NoLLM()):
        assert chat.answer("Show me the errors", run, provider).text == plain


def test_a_rephrasing_with_the_same_facts_is_used(run):
    code = chat.answer("What is pending?", run).text
    llm = Scripted(lambda text: "Here is where we stand.\n" + text.replace("Pending", "On hold"))
    reply = chat.answer("What is pending?", run, llm)
    assert reply.text.startswith("Here is where we stand.") and reply.text != code
    assert chat.facts(reply.text) == chat.facts(code)
    assert llm.requests[0].schema_name == "Rephrased"
    assert code in llm.requests[0].prompt  # the model is given the code list


def test_a_rephrasing_that_adds_a_fact_is_refused(run):
    code = chat.answer("What is pending?", run).text
    extras = ["\n- 2 more items in DMC-C-999.XML", "\nSee LRU9999.", "\nThree items.",
              "\nDeux points."]
    for extra in extras:
        llm = Scripted(lambda listing, extra=extra: listing + extra)
        assert chat.answer("What is pending?", run, llm).text == code, extra


def test_a_rephrasing_that_loses_a_fact_is_refused(run):
    code = chat.answer("What is blocked?", run).text
    llm = Scripted(lambda listing: "Something is blocked by a rule.")
    assert chat.answer("What is blocked?", run, llm).text == code


def test_a_model_that_fails_leaves_the_code_list(run):
    class Down(LLMProvider):
        name = "down"

        def _generate(self, request: Request) -> str:
            raise LLMUnavailable("down")

    code = chat.answer("What is pending?", run).text
    assert chat.answer("What is pending?", run, Down()).text == code


def test_the_rephrasing_is_logged_in_the_run_folder_and_the_log_path_is_given_back(run):
    llm = Scripted(lambda listing: listing)
    chat.answer("What is pending?", run, llm)
    assert (run.run_dir / "llm_calls.jsonl").is_file() and llm.log_path is None


def test_spelled_out_numbers_count_as_facts():
    assert chat.facts("Three items and deux points.") == {"three", "deux"}


def test_the_facts_of_a_text_are_its_figures_identifiers_and_file_names():
    text = "Pending (1):\n- DMC-B-0A3A-D_001-00_EN-US.XML: Ask about LRU2020, step stp-0003."
    assert chat.facts(text) == {"1", "DMC-B-0A3A-D_001-00_EN-US.XML", "LRU2020", "stp-0003"}
    assert chat.facts("Nothing to say here.") == set()
