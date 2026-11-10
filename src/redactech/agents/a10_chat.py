"""A10 - chat assistant: a question about the run is answered by CODE; a request becomes operations.

``answer(message, run, provider)`` first classifies the message by keywords (French and English):

* a question about the state of the run ("récap", "erreurs", "en attente", "bloqué", "recap",
  "errors", "pending", "blocked", "changed parts") is answered ONLY from queries on the run state:
  the parts changed per document, the pre-existing and introduced problems, the items put on hold
  for the customer with their comment, the requests blocked by a rule. The reply is a list of
  bullets built by code. That list is ALWAYS the answer. A configured language model may be asked
  to rephrase it; its wording is shown below the list, labelled "Reformulation du modèle (non
  vérifiée)", never instead of it, so no statement of the model replaces what the code computed.
  A message that mixes a recap and a change gets the recap and a note: send the change separately;
* anything else is a change request: it goes through A2 free text (the same checks, the same
  veracity rules) and the operations are ADDED to the run through A0: located, prepared and
  checked like the first ones. They still need the writer's decisions. Nothing is applied here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from redactech.agents import a2_freetext
from redactech.llm.base import LLMError, LLMProvider, LLMUnavailable
from redactech.models import Operation
from redactech.pipeline.orchestrator import Run
from redactech.report.build import build_report, rule_text

RECAP = ("récap", "recap", "résumé", "resume", "summary", "bilan", "où en", "state of")
TOPICS = {
    "errors": ("erreur", "error", "problème", "probleme", "problem"),
    "pending": ("en attente", "pending", "points ouverts", "open points", "on hold"),
    "blocked": ("bloqu", "blocked", "blocage"),
    "changes": ("pièces modifiées", "pieces modifiees", "changed parts", "parts changed",
                "modifiées", "what changed", "changements"),
}
ORDER = ("changes", "errors", "pending", "blocked")  # the order of the sections in a reply
EDIT_VERBS = re.compile(
    r"\b(remplace|remplacer|remplacez|replace|insère|insérer|insérez|insert|supprime|supprimer|"
    r"supprimez|delete|remove|retire|retirer|retirez|déplace|déplacer|déplacez|move|ajoute|"
    r"ajouter|ajoutez|add|modifie|modifier|modifiez|update)\b"
)
FRENCH = ("récap", "résumé", "erreur", "attente", "bloqu", "fais", "points", "pièce", "quels",
          "quelles", "donne", "liste", "modifi", "où", " les ", " des ", " et ")
MAX_REPHRASED = 4000
LABELS = {
    "fr": {
        "changes": "Pièces modifiées", "introduced": "Erreurs introduites",
        "pre_existing": "Erreurs préexistantes", "pending": "En attente du client",
        "blocked": "Bloquées par une règle", "none": "aucune", "run": "Aucun run en cours.",
        "empty": "Posez une question ou décrivez une modification.",
        "closed": "Les décisions sont closes : le run est déjà écrit.",
        "no_model": "Une demande en texte libre nécessite le modèle local ([llm] provider).",
        "added": "{n} opération(s) ajoutée(s), {m} proposition(s) à décider.",
        "nothing": "Aucune opération n'a pu être retenue.",
        "question": "Question",
        "failed": "Le modèle n'a pas pu lire la demande : {error}",
        "model_note": "Reformulation du modèle (non vérifiée)",
        "mixed": (
            "La modification demandée n'a pas été traitée : envoyez-la en message séparé."
        ),
    },
    "en": {
        "changes": "Changed parts", "introduced": "Introduced errors",
        "pre_existing": "Pre-existing errors", "pending": "Pending for the customer",
        "blocked": "Blocked by a rule", "none": "none", "run": "No run in progress.",
        "empty": "Ask a question or describe a change.",
        "closed": "Decisions are closed: the run is already written.",
        "no_model": "A free-text request needs the local model ([llm] provider).",
        "added": "{n} operation(s) added, {m} proposal(s) to decide.",
        "nothing": "No operation could be kept.",
        "question": "Question",
        "failed": "The model could not read the request: {error}",
        "model_note": "Model rephrasing (not verified)",
        "mixed": "The requested change was not processed: send it as a separate message.",
    },
}


class Rephrased(BaseModel):
    """What the model may return for a status reply: the same list, in other words."""

    text: str


@dataclass
class ChatReply:
    text: str
    operations_added: list[Operation] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # ids of the proposals / operations used
    rephrased: str = ""  # the model's wording of ``text``, if any: shown below it, NOT verified
    note: str = ""  # the label put above ``rephrased`` when it is shown

    @property
    def display(self) -> str:
        """What the writer reads: the code-computed reply, then the model's wording labelled."""
        if not self.rephrased:
            return self.text
        return f"{self.text}\n\n{self.note}:\n{self.rephrased}"


# --- classification -----------------------------------------------------------------------------


def language(message: str) -> str:
    """``fr`` when the message looks French, else ``en`` (labels of the reply)."""
    low = f" {message.casefold()} "
    return "fr" if any(word in low for word in FRENCH) else "en"


def has_edit(message: str) -> bool:
    """Does the message ask for a change (an imperative or infinitive verb, as a whole word)?"""
    return EDIT_VERBS.search(message.casefold()) is not None


def classify(message: str) -> tuple[str, list[str]]:
    """(``status`` | ``request``, the sections asked for, in reply order)."""
    low = message.casefold()
    recap = any(word in low for word in RECAP)
    topics = [name for name in ORDER if any(word in low for word in TOPICS[name])]
    if recap or (topics and not has_edit(message)):
        return "status", topics or list(ORDER)
    return "request", []


# --- the facts of a run, from the report -------------------------------------------


def _name(run: Run, key: str) -> str:
    """The file name of a document (its key when the index does not know it)."""
    doc = run.index.docs.get(key)
    return Path(doc.path).name if doc is not None else key


def _line(*parts: str) -> str:
    return "- " + ": ".join(p for p in parts if p)


def _section(title: str, lines: list[str], none: str) -> list[str]:
    return [f"{title} ({len(lines)}):", *(lines or [_line(none)])]


def status_lines(run: Run, sections: list[str], lang: str) -> tuple[list[str], list[str]]:
    """The bullet list for the sections asked, and the ids of the facts it uses."""
    labels = LABELS[lang]
    report = build_report(run.state, run.index, None)
    operations = {o.id: o for o in run.state.operations}
    lines: list[str] = []
    used: list[str] = []
    for name in sections:
        if name == "changes":
            items = []
            for doc in report.documents:
                for change in doc.changes:
                    if change.status == "rejected":
                        continue
                    op = operations.get(change.operation_id)
                    params = op.params if op is not None else {}
                    what = (f"{params['old']} → {params['new']}"
                            if "old" in params and "new" in params else change.operation)
                    items.append(_line(doc.old_name, f"{what} ({change.status})"))
                    used.append(change.proposal_id)
            lines += _section(labels["changes"], items, labels["none"])
        elif name == "errors":
            introduced = [_line(d.old_name, c.name, c.details) for d in report.documents
                          for c in d.introduced]
            old = [_line(d.old_name, c.name, c.details) for d in report.documents
                   for c in d.pre_existing]
            lines += _section(labels["introduced"], introduced, labels["none"])
            lines += _section(labels["pre_existing"], old, labels["none"])
        elif name == "pending":
            rows = [q for q in report.questions if q.status == "pending_client"]
            items = [_line(_name(run, q.document), q.text) for q in rows]
            used += [q.id for q in rows]
            lines += _section(labels["pending"], items, labels["none"])
        elif name == "blocked":
            items = [_line(_name(run, b.document), rule_text(b.rule), b.question or "")
                     for b in report.blocked]
            used += [b.proposal_id for b in report.blocked]
            lines += _section(labels["blocked"], items, labels["none"])
    return lines, used


# --- the model may rephrase, in addition, never instead ------------------------------


def rephrase(text: str, provider: LLMProvider | None, log_path: Path | None) -> str:
    """The model's wording of the code list, or "" (no model, a failure, nothing usable).

    It is NOT checked: the reply of the assistant is always the code list, and this wording is
    shown below it, labelled as the model's (see ``ChatReply.display``).
    """
    if provider is None or provider.name == "none":
        return ""
    previous = provider.log_path
    provider.log_path = log_path or previous
    try:
        reply = provider.complete_json(
            "Rephrase this list in the same language as its titles. Keep every item and add "
            "nothing.\n\n" + text,
            Rephrased,
            system="You rewrite a status list for a technical writer. You never add information.",
        )
    except LLMError:
        return ""
    finally:
        provider.log_path = previous
    candidate = getattr(reply, "text", "").strip()
    return candidate if 0 < len(candidate) <= MAX_REPHRASED else ""


# --- the replies --------------------------------------------------------------------


def answer(message: str, run: Run | None, provider: LLMProvider | None = None) -> ChatReply:
    """The reply to a message of the writer (see the module docstring)."""
    lang = language(message)
    labels = LABELS[lang]
    if not message.strip():
        return ChatReply(labels["empty"])
    if run is None:
        return ChatReply(labels["run"])
    kind, sections = classify(message)
    if kind == "status":
        lines, used = status_lines(run, sections, lang)
        text = "\n".join(lines)
        wording = rephrase(text, provider, run.run_dir / "llm_calls.jsonl")
        if has_edit(message):  # a recap and a change in one message: only the recap is answered
            text += "\n\n" + labels["mixed"]
        return ChatReply(text, sources=used, rephrased=wording, note=labels["model_note"])
    return _request_reply(message.strip(), run, provider, lang)


def _request_reply(text: str, run: Run, provider: LLMProvider | None, lang: str) -> ChatReply:
    labels = LABELS[lang]
    if run.state.stage not in ("proposals_ready", "reviewed"):
        return ChatReply(labels["closed"])
    if provider is None or provider.name == "none":
        return ChatReply(labels["no_model"])
    previous = provider.log_path
    provider.log_path = run.run_dir / "llm_calls.jsonl"
    try:
        found = a2_freetext.interpret_full(text, run.index, provider)
    except LLMUnavailable:
        return ChatReply(labels["no_model"])
    except LLMError as exc:
        return ChatReply(labels["failed"].format(error=exc))
    finally:
        provider.log_path = previous
    added, proposals = run.add_operations(found.operations)
    for question in found.questions:
        run.note_question(question)
    lines = []
    if added:
        pending = [p for p in proposals if p.id in run.pending_ids()]
        lines.append(labels["added"].format(n=len(added), m=len(pending)))
    else:
        lines.append(labels["nothing"])
    lines += [f"- {labels['question']}: {q}" for q in found.questions]
    return ChatReply("\n".join(lines), operations_added=added, sources=[p.id for p in proposals])
