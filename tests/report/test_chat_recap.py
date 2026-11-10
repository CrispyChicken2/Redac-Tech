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
NL = chr(10)
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


# --- the model may rephrase, in addition, never instead ----------------------------------------


FALSE_CLAIM = (
    "Erreurs introduites (0) : des erreurs graves ont été détectées. "
    "Erreurs préexistantes (0). "
    "En attente du client (1) : tout a été validé par le client."
)


def test_without_a_model_the_reply_is_the_code_list_alone(run):
    plain = chat.answer("Show me the errors", run)
    for provider in (None, NoLLM()):
        reply = chat.answer("Show me the errors", run, provider)
        assert reply.text == plain.text and reply.rephrased == "" and reply.display == plain.text


def test_a_rephrasing_is_shown_below_the_code_list_and_labelled(run):
    code = chat.answer("What is pending?", run).text
    llm = Scripted(lambda text: "Here is where we stand." + NL + text.replace("Pending", "On hold"))
    reply = chat.answer("What is pending?", run, llm)
    assert reply.text == code  # the answer is the code list, unchanged
    assert reply.rephrased.startswith("Here is where we stand.")
    label = "Model rephrasing (not verified):"
    assert reply.display == code + NL + NL + label + NL + reply.rephrased
    assert reply.display.startswith(code)
    assert llm.requests[0].schema_name == "Rephrased" and code in llm.requests[0].prompt


def test_the_label_is_french_for_a_french_message(run):
    llm = Scripted(lambda text: "Voici où nous en sommes.")
    reply = chat.answer("Quelles demandes sont bloquées ?", run, llm)
    assert reply.display.startswith(reply.text)
    label = "Reformulation du modèle (non vérifiée):"
    assert reply.display.endswith(label + NL + "Voici où nous en sommes.")


def test_a_false_claim_in_plain_words_never_replaces_the_code_list(run):
    """The model's wording is only an addition: a claim with no figure cannot change the answer."""
    run.state.proposals = []
    code = chat.answer("Fais-moi un récap des erreurs et des points en attente", run).text
    assert "- aucune" in code and "graves" not in code
    llm = Scripted(lambda text: FALSE_CLAIM)
    reply = chat.answer("Fais-moi un récap des erreurs et des points en attente", run, llm)
    assert reply.text == code  # unchanged, and it still says "aucune"
    assert reply.display.startswith(code)
    shown_after = reply.display[len(code):]
    assert "Reformulation du modèle (non vérifiée)" in shown_after and "graves" in shown_after
    assert "graves" not in reply.text and "validé" not in reply.text


def test_a_model_that_fails_leaves_only_the_code_list(run):
    class Down(LLMProvider):
        name = "down"

        def _generate(self, request: Request) -> str:
            raise LLMUnavailable("down")

    code = chat.answer("What is pending?", run).text
    reply = chat.answer("What is pending?", run, Down())
    assert reply.text == code and reply.rephrased == "" and reply.display == code


def test_an_empty_or_huge_rephrasing_is_ignored(run):
    for wording in ("   ", "x" * (chat.MAX_REPHRASED + 1)):
        reply = chat.answer("What is pending?", run, Scripted(lambda text, w=wording: w))
        assert reply.rephrased == "" and reply.display == reply.text


def test_the_rephrasing_is_logged_in_the_run_folder_and_the_log_path_is_given_back(run):
    llm = Scripted(lambda listing: listing)
    chat.answer("What is pending?", run, llm)
    assert (run.run_dir / "llm_calls.jsonl").is_file() and llm.log_path is None


# --- a recap and a change in one message -----------------------------------


def test_the_recap_is_answered_and_the_change_is_sent_back(run):
    reply = chat.answer("Remplace LRU1010 par LRU2020 et fais un récap des erreurs", run)
    code = chat.answer("Fais un récap des erreurs", run).text
    assert reply.text == code + NL + NL + (
        "La modification demandée n'a pas été traitée : envoyez-la en message séparé.")
    assert reply.operations_added == []
    english = chat.answer("Replace LRU1010 with LRU2020 and give me a recap of the errors", run)
    note = "The requested change was not processed: send it as a separate message."
    assert english.text.endswith(note)
    assert english.text.startswith("Introduced errors (1):")


def test_the_model_is_not_asked_to_read_the_change_of_a_mixed_message(run):
    llm = Scripted(lambda text: "reworded")
    chat.answer("Replace LRU1010 with LRU2020 and give me a recap of the errors", run, llm)
    assert {request.schema_name for request in llm.requests} == {"Rephrased"}
    assert "LRU2020" not in llm.requests[0].prompt  # the request text is not sent along


def test_a_recap_that_only_mentions_a_past_change_has_no_note(run):
    for message in ("Récap des pièces remplacées", "Recap of the replaced parts"):
        reply = chat.answer(message, run)
        assert "envoyez-la" not in reply.text and "send it as" not in reply.text


def test_the_edit_verbs_are_whole_words():
    assert chat.has_edit("Remplace LRU1010 par LRU2020") and chat.has_edit("please REPLACE it")
    assert chat.has_edit("Supprimer l'étape") and chat.has_edit("add a spare")
    assert not chat.has_edit("Récap des pièces remplacées")
    assert not chat.has_edit("Recap of the replaced and added parts")
    assert not chat.has_edit("the address of the manual")
