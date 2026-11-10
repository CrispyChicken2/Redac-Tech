"""Small helpers of the UI: labels, badges, the request form, the delivery files.

Pure functions, no streamlit import: everything here can be imported and tested without
starting Streamlit. User-facing labels are in French; identifiers are English.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from redactech.agents.a2_mapping import REQUIRED
from redactech.models import Proposal, SourceRef, Zone
from redactech.pipeline.orchestrator import Run

VIEW_XML, VIEW_PUBLISHED, VIEW_BOTH = "XML", "Publiée (IETP)", "Côte à côte"
VIEWS = (VIEW_XML, VIEW_PUBLISHED, VIEW_BOTH)
STATUS_LABELS = {
    "proposed": "À décider",
    "accepted": "Acceptée",
    "edited": "Éditée",
    "rejected": "Rejetée",
    "pending_client": "En attente du client",
    "blocked_by_rule": "Bloquée par une règle",
}
MODE_LABELS = {
    "none": "Aucune (le fichier garde son numéro)",
    "in_work": "Travail en cours (inWork + 1)",
    "new_issue": "Nouvelle issue (consolidation)",
}
KIND_LABELS = {
    "replace_part": "Remplacer un numéro de pièce",
    "replace_text": "Remplacer un texte",
    "insert_step": "Insérer une étape",
    "delete_step": "Supprimer une étape",
    "move_step": "Déplacer une étape",
    "update_ref": "Modifier une référence",
    "add_requirement": "Ajouter une exigence",
    "remove_requirement": "Retirer une exigence",
}
FIELD_LABELS = {
    "old": "Ancienne valeur",
    "new": "Nouvelle valeur",
    "para": "Texte du paragraphe",
    "note": "Texte d'une note (facultatif)",
    "after_id": "Après l'étape (id)",
    "before_id": "Avant l'étape (id)",
    "step_id": "Étape (id)",
    "dm_code": "Code DM (JSON, ex. {\"infoCode\": \"520\"})",
    "internal_ref_id": "Nouvelle cible (id)",
    "target_type": "Type de cible (facultatif)",
    "requirement": "Genre (spare, supply, tool)",
    "part_number": "Numéro de pièce",
    "manufacturer_code": "Code fabricant",
    "quantity": "Quantité",
    "name": "Nom (facultatif)",
    "id": "Id de l'exigence",
}
# optional parameters offered next to the required ones
OPTIONAL_FIELDS = {
    "insert_step": ("note",),
    "update_ref": ("target_type",),
    "add_requirement": ("name",),
}
JSON_FIELDS = ("dm_code",)  # entered as JSON text
BADGE_CSS = (
    ".rt-badge{display:inline-block;border-radius:.7rem;padding:0 .6rem;margin:0 .2rem .2rem 0;"
    "font-size:.78rem;font-family:sans-serif}"
    ".rt-badge-pre_existing{background:#e4e4e4;color:#555}"
    ".rt-badge-introduced{background:#fbd5d5;color:#900;font-weight:bold}"
    ".rt-badge-illustration{background:#ffe9b8;color:#7a5200}"
)


@dataclass(frozen=True)
class Badge:
    label: str
    kind: str  # pre_existing | introduced | illustration


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    required: bool


def badges(proposal: Proposal, zone: Zone | None = None) -> list[Badge]:
    """Check badges of a proposal: pre-existing (grey), introduced (red), figure to check."""
    found: list[Badge] = []
    if zone is not None and zone.kind == "illustration":
        found.append(Badge("À vérifier (illustration)", "illustration"))
    for check in proposal.checks:
        if check.ok or check.name == "illustration":
            continue
        if check.origin == "introduced":
            found.append(Badge(f"Introduit : {check.name}", "introduced"))
        else:
            found.append(Badge(f"Préexistant : {check.name}", "pre_existing"))
    return list(dict.fromkeys(found))


def badge_html(badge: Badge) -> str:
    return f'<span class="rt-badge rt-badge-{escape(badge.kind)}">{escape(badge.label)}</span>'


def badges_html(proposal: Proposal, zone: Zone | None = None) -> str:
    return "".join(badge_html(b) for b in badges(proposal, zone))


# --- request form ----------------------------------------------------------------------------


def form_kinds() -> list[str]:
    """Operation kinds the form offers (the ones the pipeline knows)."""
    return list(REQUIRED)


def form_fields(kind: str) -> list[FormField]:
    """Fields of the form for an operation kind: the required ones, then the optional ones."""
    fields: list[FormField] = []
    for need in REQUIRED[kind]:
        names = need if isinstance(need, tuple) else (need,)
        # "one of" parameters (after_id / before_id ...): all offered, none required alone
        for name in names:
            fields.append(FormField(name, FIELD_LABELS.get(name, name), len(names) == 1))
    for name in OPTIONAL_FIELDS.get(kind, ()):
        fields.append(FormField(name, FIELD_LABELS.get(name, name), False))
    return fields


def needs_target(kind: str) -> bool:
    """Every operation but the part replacement is applied to a chosen document."""
    return kind != "replace_part"


def build_form(
    kind: str,
    ref: SourceRef | None,
    values: dict[str, str],
    target: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """The form dict that the pipeline reads (``a2_mapping.from_form``).

    ``target`` is an element id, or an XPath when it starts with ``/``. Empty values are left
    out; the fields in ``JSON_FIELDS`` are parsed as JSON (``ValueError`` if invalid).
    """
    params: dict[str, Any] = {}
    for name, value in values.items():
        text = (value or "").strip()
        if not text:
            continue
        if name in JSON_FIELDS:
            try:
                params[name] = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{FIELD_LABELS.get(name, name)}: {exc}") from exc
        else:
            params[name] = text
    form: dict[str, Any] = {"kind": kind, "params": params}
    if reason.strip():
        form["reason"] = reason.strip()
    if ref is not None and needs_target(kind):
        spec: dict[str, Any] = {"ref": ref.model_dump()}
        if target.strip().startswith("/"):
            spec["xpath"] = target.strip()
        elif target.strip():
            spec["element_id"] = target.strip()
        form["target"] = spec
    return form


def describe_form(form: dict[str, Any]) -> str:
    """One line for the list of operations of the request."""
    params = ", ".join(f"{k}={v}" for k, v in (form.get("params") or {}).items())
    return f"{KIND_LABELS.get(form['kind'], form['kind'])} ({params})"


# --- proposals and delivery ----------------------------------------------------------------------


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def counts_by_status(run: Run) -> dict[str, int]:
    """Number of proposals per status (flag-only illustrations excluded)."""
    flags = {z.id for z in run.state.zones if z.kind == "illustration"}
    counts: dict[str, int] = {}
    for proposal in run.state.proposals:
        if proposal.zone_id not in flags:
            counts[proposal.status] = counts.get(proposal.status, 0) + 1
    return counts


def can_decide(run: Run) -> bool:
    """Decisions are possible between the preparation and the write."""
    return run.state.stage in ("proposals_ready", "reviewed")


def can_write(run: Run) -> bool:
    """The write needs a chosen policy, nothing left to decide, and a stage that allows it."""
    return can_decide(run) and run.state.version_policy is not None and not run.pending_ids()


def zip_outputs(out_dir: Path | str) -> bytes:
    """A zip (in memory) of the data modules written into ``out_dir``."""
    buffer = io.BytesIO()
    folder = Path(out_dir)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if path.is_file():
                    archive.write(path, arcname=path.name)
    return buffer.getvalue()
