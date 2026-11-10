"""A2 free text: a change request in French or English -> operations, checked by code.

The language model (through ``redactech.llm``) only PROPOSES operations as typed JSON
(``OpsResponse``). The code then checks every one of them, and nothing the model says is trusted:

* every quote must be an exact piece of the request (else the operation becomes a question);
* every value of the operation (a new part number, a text, an id, a quantity ...) must appear in the
  request text: this is the veracity rule (OBJ-3), so an invented value never gets through; a
  value that does not is turned into a question;
* the ``old`` value of a replacement must exist in the documentation (else a "not found" question);
* the target document must be one of the documents of the index;
* a required parameter that is missing becomes a question.

Ambiguities the model reports are questions too. The operations that survive are ordinary
``Operation`` objects with their source spans (offsets and quote in the request): they go through
A0, A4, A5, A7 and the writer's decision like the operations of a mapping table. Nothing is applied
here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from redactech.agents.a2_mapping import REQUIRED
from redactech.llm.base import LLMProvider
from redactech.models import Operation, SourceSpan, Target
from redactech.s1000d.index import CorpusIndex, find_part
from redactech.s1000d.text import contains_token

PROMPT_FILE = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "a2_freetext.md"
SOURCE_DOC = "free_text"
MAX_PARTS = 80  # part numbers listed in the prompt
MAX_DOCS = 60  # documents listed in the prompt
REQUIREMENT_KEYWORDS = ("spare", "supply", "tool", "supportEquipment")
OPTIONAL = {
    "insert_step": ("note",),
    "update_ref": ("target_type",),
    "add_requirement": ("name",),
}


class OpSpec(BaseModel):
    """One operation as the model proposes it (not trusted)."""

    kind: Literal[
        "replace_part", "replace_text", "insert_step", "delete_step", "move_step",
        "update_ref", "add_requirement", "remove_requirement",
    ]
    params: dict[str, str] = Field(default_factory=dict)
    target_doc: str | None = None
    target_id: str | None = None
    reason: str = ""
    quotes: list[str] = Field(default_factory=list)


class OpsResponse(BaseModel):
    """The JSON the model must return."""

    operations: list[OpSpec] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


@dataclass
class Interpretation:
    operations: list[Operation] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)


def system_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8").strip()


def norm(text: str) -> str:
    """Whitespace-collapsed, case-folded text, for comparing values with the request."""
    return " ".join(text.split()).casefold()


def appears(text: str, value: str) -> bool:
    """Is ``value`` in the request? A single word must be a whole word ("2" is not in "2020")."""
    if " " not in value.strip() and len(value) <= 40:
        return contains_token(text, value) or contains_token(norm(text), norm(value))
    return norm(value) in norm(text)


def doc_names(index: CorpusIndex) -> list[tuple[str, str]]:
    """(document key, file name) of the data modules, sorted by file name."""
    return sorted(
        ((key, Path(doc.path).name) for key, doc in index.docs.items() if doc.role == "dm"),
        key=lambda item: item[1],
    )


def build_prompt(text: str, index: CorpusIndex) -> str:
    """The user prompt: the request and a short summary of the documentation."""
    docs = doc_names(index)[:MAX_DOCS]
    parts = sorted(index.parts)[:MAX_PARTS]
    lines = ["Request:", "<<<", text, ">>>", "", "Documents (key | file name):"]
    lines += [f"- {key} | {name}" for key, name in docs] or ["- (none)"]
    lines += ["", "Part numbers found in the documentation:", ", ".join(parts) or "(none)"]
    return "\n".join(lines)


def resolve_doc(index: CorpusIndex, name: str | None) -> str | None:
    """The key of the data module named ``name`` (key, doc key, file name or stem), else None."""
    if not name:
        return None
    wanted = name.strip().casefold()
    found = [
        key
        for key, doc in index.docs.items()
        if doc.role == "dm"
        and wanted in {key.casefold(), doc.ref.doc_key.casefold(), Path(doc.path).name.casefold(),
                       Path(doc.path).stem.casefold()}
    ]
    return found[0] if len(found) == 1 else None


def missing_params(kind: str, params: dict[str, str]) -> list[str]:
    missing = []
    for need in REQUIRED[kind]:
        names = need if isinstance(need, tuple) else (need,)
        if not any(params.get(n) not in (None, "") for n in names):
            missing.append(" or ".join(names))
    return missing


def _known_params(kind: str) -> set[str]:
    names: set[str] = set(OPTIONAL.get(kind, ()))
    for need in REQUIRED[kind]:
        names.update(need if isinstance(need, tuple) else (need,))
    return names


def _old_exists(index: CorpusIndex, kind: str, old: str) -> bool:
    if kind == "replace_part":
        return bool(find_part(index, old))
    return any(old in block.text for block in index.texts)


def _values(params: dict[str, str]) -> list[str]:
    """The values to check against the request (a dm_code given as JSON is opened up)."""
    found: list[str] = []
    for name, value in params.items():
        if name == "dm_code":
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                found.append(value)
                continue
            if isinstance(parsed, dict):
                found.extend(str(v) for v in parsed.values())
        elif name == "requirement" and value in REQUIREMENT_KEYWORDS:
            continue  # a keyword of the operation, not a value taken from a document
        else:
            found.append(value)
    return found


def check_operation(spec: OpSpec, text: str, index: CorpusIndex) -> tuple[Operation | None, str]:
    """The operation if it passes every check, else None and the question to ask instead."""
    label = spec.kind
    quotes = [q for q in spec.quotes if q.strip()]
    if not quotes:
        return None, f"The {label} operation has no quote from your request; please rephrase."
    for quote in quotes:
        if quote not in text:
            return None, f"A quote for the {label} operation is not in your request: {quote!r}."
    params = {k: v.strip() for k, v in spec.params.items() if k in _known_params(spec.kind)}
    absent = [v for v in _values(params) if v and not appears(text, v)]
    if spec.target_id and not appears(text, spec.target_id):
        absent.append(spec.target_id)
    if absent:
        shown = ", ".join(repr(v) for v in absent)
        return None, (
            f"The {label} operation uses {shown}, which is not in your request. "
            "Please give the exact value."
        )
    missing = missing_params(spec.kind, params)
    if missing:
        return None, f"The {label} operation lacks: {', '.join(missing)}. What should it be?"
    old = params.get("old")
    if old and not _old_exists(index, spec.kind, old):
        return None, f"{old!r} was not found in the documentation."
    target = Target()
    if spec.kind != "replace_part":
        key = resolve_doc(index, spec.target_doc)
        if key is None:
            return None, f"Which document does the {label} operation concern?"
        target = Target(ref=index.docs[key].ref, element_id=spec.target_id)
    spans = [
        SourceSpan(doc=SOURCE_DOC, start=text.find(q), end=text.find(q) + len(q), quote=q)
        for q in quotes
    ]
    operation = Operation(
        id="op-0000",  # numbered by interpret_full
        kind=spec.kind,
        target=target,
        params=params,
        rationale=spec.reason.strip() or f"{spec.kind} requested in free text",
        source=spans,
    )
    return operation, ""


def interpret_full(text: str, index: CorpusIndex, provider: LLMProvider) -> Interpretation:
    """Ask the model, check every operation, and return the survivors and the questions."""
    request = text.strip()
    if not request:
        return Interpretation(questions=["The request is empty."])
    response = provider.complete_json(build_prompt(request, index), OpsResponse,
                                      system=system_prompt())
    assert isinstance(response, OpsResponse)
    result = Interpretation()
    for spec in response.operations:
        operation, question = check_operation(spec, request, index)
        if operation is None:
            result.questions.append(question)
        else:
            number = len(result.operations) + 1
            result.operations.append(operation.model_copy(update={"id": f"op-{number:04d}"}))
    result.questions += [q.strip() for q in response.questions if q.strip()]
    return result


def interpret(text: str, index: CorpusIndex, provider: LLMProvider) -> list[Operation]:
    """The checked operations of a free-text request (see ``interpret_full`` for the questions)."""
    return interpret_full(text, index, provider).operations
