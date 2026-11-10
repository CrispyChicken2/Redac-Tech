"""Streamlit UI, Document mode: ``streamlit run src/redactech/ui/app.py``.

The UI holds no business logic: it calls the pipeline (``pipeline/orchestrator.py``), the views
(``render/``) and the delivery files (``report/``) through ``ui/state.py`` and
``ui/components.py``. There is no automatic acceptance here: ``auto_accept`` is never set and
"Tout accepter" only accepts what the pipeline calls certain and clean. Every widget has a
stable ``key`` so that a test (``streamlit.testing``) can find it. Importing this module starts
nothing: the page is built by ``main()`` only.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from lxml import etree

from redactech.agents.a10_chat import answer
from redactech.config import load_config
from redactech.llm import get_provider
from redactech.pipeline import orchestrator as orch
from redactech.render.published import PUBLISHED_CSS, render_published
from redactech.render.side_by_side import SIDE_CSS, render_before_after, render_side_by_side
from redactech.render.xml_view import XML_CSS, render_xml
from redactech.report.build import question_entries
from redactech.report.export import export_questions
from redactech.s1000d.index import ref_key
from redactech.ui import components as comp
from redactech.ui import state as ui_state

PAGE_CSS = XML_CSS + PUBLISHED_CSS + SIDE_CSS + comp.BADGE_CSS
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PROJECT, RUN, FORM_OPS, FLASH = "rt_project", "rt_run", "rt_form_ops", "rt_flash"
CHAT = "rt_chat"


# --- session ---------------------------------------------------------------------------------


def project() -> ui_state.Project | None:
    return st.session_state.get(PROJECT)


def current_run() -> orch.Run | None:
    return st.session_state.get(RUN)


def flash(kind: str, text: str) -> None:
    """A message shown at the top of the next run of the script (after a rerun)."""
    st.session_state[FLASH] = (kind, text)


def show_flash() -> None:
    message = st.session_state.pop(FLASH, None)
    if message is not None:
        kind, text = message
        getattr(st, kind)(text)


def reset_run() -> None:
    st.session_state.pop(RUN, None)
    st.session_state.pop(CHAT, None)
    st.session_state[FORM_OPS] = []


# --- sidebar: the project --------------------------------------------------------------------


def sidebar() -> None:
    st.sidebar.header("Projet")
    path = st.sidebar.text_input(
        "Fichier workspace", value=ui_state.default_workspace_path(), key="ws_path"
    )
    if st.sidebar.button("Charger le projet", key="ws_load"):
        try:
            st.session_state[PROJECT] = ui_state.load_project(path)
            reset_run()
            flash("success", "Projet chargé.")
        except (OSError, ValueError, KeyError) as exc:
            st.sidebar.error(f"Impossible de charger le projet : {exc}")
        else:
            st.rerun()
    current = project()
    if current is None:
        st.sidebar.info("Chargez un workspace pour commencer.")
        return
    sources_panel(current)
    uploads_panel(current)
    brex_panel(current)
    baseline_panel(current)


def sources_panel(current: ui_state.Project) -> None:
    st.sidebar.subheader("Sources")
    for source_id, folder, writable, roles in ui_state.source_rows(current):
        counts = ", ".join(f"{role} : {n}" for role, n in roles.items()) or "vide"
        mode = "modifiable" if writable else "lecture seule"
        st.sidebar.markdown(f"**{source_id}** ({mode})  \n`{folder}`  \n{counts}")


def uploads_panel(current: ui_state.Project) -> None:
    st.sidebar.subheader("Ajouter des fichiers")
    files = st.sidebar.file_uploader(
        "Déposer des DM, BREX ou ICN", accept_multiple_files=True, key="upload_files"
    )
    if st.sidebar.button("Importer", key="upload_import", disabled=not files):
        saved = ui_state.add_uploads(current, [(f.name, f.getvalue()) for f in files])
        reset_run()
        lines = [
            f"{u.name} : {u.role}" if u.saved else f"{u.name} refusé ({u.problem})" for u in saved
        ]
        flash("info", "Fichiers importés :\n\n" + "\n\n".join(lines))
        st.rerun()
    for upload in current.uploads:
        st.sidebar.caption(f"{upload.name} : {upload.role}")


def brex_panel(current: ui_state.Project) -> None:
    st.sidebar.subheader("Changer de BREX")
    brex_file = st.sidebar.file_uploader(
        "Déposer un BREX (022)", accept_multiple_files=False, key="brex_upload"
    )
    if st.sidebar.button("Remplacer le BREX", key="brex_swap", disabled=brex_file is None):
        try:
            ui_state.swap_project_brex(current, brex_file.name, brex_file.getvalue())
        except ValueError as exc:
            st.sidebar.error(f"BREX refusé : {exc}")
        else:
            reset_run()
            flash("success", "BREX remplacé : chaînes résolues, état initial recalculé.")
            st.rerun()
    for swapped in current.brex_swaps:
        st.sidebar.caption(f"BREX remplacé par {swapped.name}")


def baseline_panel(current: ui_state.Project) -> None:
    st.sidebar.subheader("Problèmes préexistants")
    summary = ui_state.baseline_summary(current)
    if not summary:
        st.sidebar.caption("Aucun problème préexistant.")
    for doc in summary:
        label = f"{doc.name} : {doc.errors} erreur(s), {doc.warnings} avertissement(s)"
        with st.sidebar.expander(label):
            for item in doc.items:
                st.write(f"{item.severity} — {item.name} : {item.details}")


# --- request ---------------------------------------------------------------------------------


def request_tab(current: ui_state.Project) -> None:
    run = current_run()
    if run is not None:
        st.write(f"Run en cours : `{run.state.run_id}` ({run.state.stage}).")
        operations_table(run)
        for question in run.free_text_questions():
            st.warning(f"Question : {question}")
        if run.state.stage == "ops_proposed":
            versioning_panel(run)
        if st.button("Nouvelle demande", key="new_request"):
            reset_run()
            st.rerun()
        return
    mode = st.radio(
        "Demande", ["Tableau CSV/XLSX", "Formulaire"], horizontal=True, key="request_mode"
    )
    mapping: tuple[str, bytes] | None = None
    if mode == "Tableau CSV/XLSX":
        uploaded = st.file_uploader(
            "Tableau de correspondance (colonnes old, new, kind, reason)",
            type=["csv", "xlsx"],
            key="mapping_upload",
        )
        if uploaded is not None:
            mapping = (uploaded.name, uploaded.getvalue())
    else:
        form_panel(current)
    forms = st.session_state.get(FORM_OPS) or None
    free_text_panel(current)
    ready = mapping is not None if mode == "Tableau CSV/XLSX" else forms is not None
    if st.button("Préparer", key="prepare", disabled=not ready):
        try:
            started = ui_state.start_run(
                current, mapping=mapping if mode == "Tableau CSV/XLSX" else None,
                forms=None if mode == "Tableau CSV/XLSX" else forms,
            )
        except Exception as exc:  # a bad mapping or form: shown, never a crash
            st.error(f"Demande refusée : {exc}")
        else:
            st.session_state[RUN] = started
            st.rerun()


def free_text_panel(current: ui_state.Project) -> None:
    """A request in plain French or English: only with a local model configured."""
    st.subheader("Texte libre")
    if load_config().llm.provider == "none":
        st.info("Le texte libre nécessite le modèle local ([llm] provider dans config.toml).")
        return
    text = st.text_area("Décrivez la modification (français ou anglais)", key="free_text")
    if st.button("Préparer (texte libre)", key="prepare_free_text", disabled=not text.strip()):
        try:
            started = ui_state.start_run(current, free_text=text)
        except Exception as exc:  # the model is missing or answered badly: shown, never a crash
            st.error(f"Demande refusée : {exc}")
        else:
            st.session_state[RUN] = started
            st.rerun()


def form_panel(current: ui_state.Project) -> None:
    ops: list[dict[str, Any]] = st.session_state.setdefault(FORM_OPS, [])
    kind = st.selectbox(
        "Opération", comp.form_kinds(), format_func=lambda k: comp.KIND_LABELS.get(k, k),
        key="form_kind",
    )
    choices = ui_state.document_choices(current)
    key = None
    target = ""
    if comp.needs_target(kind):
        key = st.selectbox(
            "Document", [k for k, _ in choices], key="form_doc",
            format_func=lambda k: dict(choices).get(k, k),
        )
        target = st.text_input("Élément visé (id, ou XPath en /)", key="form_target")
    values = {
        field.name: st.text_input(
            field.label + ("" if field.required else " (facultatif)"),
            key=f"form_{kind}_{field.name}",
        )
        for field in comp.form_fields(kind)
    }
    reason = st.text_input("Motif", key="form_reason")
    if st.button("Ajouter l'opération", key="form_add"):
        try:
            ref = ui_state.doc_ref(current, key) if key else None
            ops.append(comp.build_form(kind, ref, values, target, reason))
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    for number, form in enumerate(ops):
        columns = st.columns([6, 1])
        columns[0].write(f"{number + 1}. {comp.describe_form(form)}")
        if columns[1].button("Retirer", key=f"form_remove_{number}"):
            ops.pop(number)
            st.rerun()


def operations_table(run: orch.Run) -> None:
    rows = [
        {"id": op.id, "opération": comp.KIND_LABELS.get(op.kind, op.kind), "motif": op.rationale}
        for op in run.base_operations()
    ]
    st.table(rows)


def versioning_panel(run: orch.Run) -> None:
    """The versioning choice: required before any proposal is prepared."""
    st.subheader("Politique de versionnement")
    suggestion = run.suggestion()
    st.write(f"Suggestion : **{comp.MODE_LABELS.get(suggestion.suggested)}**")
    for reason in suggestion.reasons:
        st.caption(reason)
    modes = list(ui_state.MODES)
    mode = st.radio(
        "Politique",
        modes,
        index=modes.index(suggestion.suggested) if suggestion.suggested in modes else 0,
        format_func=lambda m: comp.MODE_LABELS[m],
        key="policy_radio",
    )
    if st.button("Confirmer et préparer les propositions", key="policy_confirm"):
        try:
            ui_state.confirm_policy(run, mode)
        except orch.PipelineError as exc:
            st.error(str(exc))
        else:
            flash("success", "Propositions prêtes.")
            st.rerun()


# --- document and proposals ------------------------------------------------------------------


def document_tab(current: ui_state.Project) -> None:
    choices = ui_state.document_choices(current)
    if not choices:
        st.info("Aucun module de données dans ce projet.")
        return
    names = dict(choices)
    left, right = st.columns([3, 2])
    with left:
        key = st.selectbox(
            "Document", [k for k, _ in choices], format_func=lambda k: names[k], key="doc_select"
        )
        view = st.radio("Vue", comp.VIEWS, horizontal=True, key="view_mode")
        hide = st.checkbox("Masquer les suppressions", key="hide_deleted")
        run = current_run()
        marks = ui_state.highlight_ids(run, key) if run is not None else []
        show_document(current, key, view, hide, marks)
    with right:
        proposals_panel(current, key, view)


def show_document(current: ui_state.Project, key: str, view: str, hide: bool, marks: list) -> None:
    try:
        doc = ui_state.load_document(current, key)
        if view == comp.VIEW_XML:
            body = render_xml(doc, marks)
        elif view == comp.VIEW_PUBLISHED:
            body = render_published(doc, show_deleted=not hide)
        else:
            body = render_side_by_side(
                render_xml(doc, marks), render_published(doc, show_deleted=not hide),
                ("XML", "Publiée (IETP)"),
            )
    except (etree.LxmlError, OSError, ValueError) as exc:
        st.error(f"Impossible d'afficher le document : {exc}")
        return
    st.markdown(f"<style>{PAGE_CSS}</style>{body}", unsafe_allow_html=True)


def proposals_panel(current: ui_state.Project, doc_key: str, view: str) -> None:
    run = current_run()
    st.subheader("Propositions")
    if run is None or run.state.stage in ("indexed", "ops_proposed"):
        st.info("Préparez une demande (onglet Demande) et choisissez le versionnement.")
        return
    only_here = st.checkbox("Seulement ce document", value=True, key="only_this_doc")
    if comp.can_decide(run) and st.button("Tout accepter", key="accept_all"):
        before = len(run.pending_ids())
        done = run.accept_all()
        left = len(run.pending_ids())
        flash("info", f"{len(done)} acceptée(s) sur {before} ; {left} restent à décider.")
        st.rerun()
    blocked_panel(run)
    zones = {z.id: z for z in run.state.zones}
    shown = 0
    for proposal in run.state.proposals:
        if proposal.status == "blocked_by_rule":
            continue
        if only_here and ref_key(proposal.ref) != doc_key:
            continue
        shown += 1
        proposal_card(run, proposal, zones.get(proposal.zone_id), view)
    if not shown:
        st.caption("Aucune proposition pour ce document.")


def blocked_panel(run: orch.Run) -> None:
    rows = [q for q in question_entries(run.state) if q.status == "blocked_by_rule"]
    with st.expander(f"Bloquées par une règle ({len(rows)})", expanded=bool(rows)):
        if not rows:
            st.caption("Aucune demande bloquée.")
        for row in rows:
            st.markdown(f"**{row.id}** — règle : {row.rule}")
            st.write(row.text)
            if comp.can_decide(run) and st.button(
                "Poser la question au client", key=f"ask_{row.id}"
            ):
                apply_decision(run, lambda row=row: run.decide(row.id, "pending_client", row.text))


def proposal_card(run: orch.Run, proposal: Any, zone: Any, view: str) -> None:
    pid = proposal.id
    title = f"{pid} — {comp.status_label(proposal.status)}"
    with st.expander(title, expanded=proposal.status == "proposed"):
        badges = comp.badges_html(proposal, zone)
        if badges:
            st.markdown(f"<style>{comp.BADGE_CSS}</style>{badges}", unsafe_allow_html=True)
        side = "published" if view == comp.VIEW_PUBLISHED else "xml"
        st.markdown(
            f"<style>{PAGE_CSS}</style>{render_before_after(proposal, side)}",
            unsafe_allow_html=True,
        )
        if proposal.reviewer_comment:
            st.caption(f"Commentaire : {proposal.reviewer_comment}")
        if comp.can_decide(run):
            decision_controls(run, proposal, flag_only=run.is_flag(proposal))


def decision_controls(run: orch.Run, proposal: Any, flag_only: bool = False) -> None:
    """Accept / edit / reject / pending; a flag-only illustration can only be acknowledged."""
    pid = proposal.id
    columns = st.columns(4)
    if columns[0].button("Accepter", key=f"accept_{pid}"):
        apply_decision(run, lambda: run.decide(pid, "accepted"))
    if not flag_only:
        edit_and_reject(run, proposal, columns)
    comment = st.text_input("Commentaire pour le client", key=f"pending_comment_{pid}")
    if columns[3].button("En attente", key=f"pending_{pid}"):
        if not comment.strip():
            st.warning("Un commentaire est obligatoire pour mettre en attente.")
        else:
            apply_decision(run, lambda: run.decide(pid, "pending_client", comment.strip()))


def edit_and_reject(run: orch.Run, proposal: Any, columns: list) -> None:
    pid = proposal.id
    edited = st.text_area(
        "Édition du XML", value=proposal.edited_xml or proposal.after_xml, key=f"edit_text_{pid}"
    )
    if columns[1].button("Éditer", key=f"edit_{pid}"):
        apply_decision(run, lambda: run.decide(pid, "edited", None, edited))
    reason = st.text_input("Motif du rejet", key=f"reject_reason_{pid}")
    if columns[2].button("Rejeter", key=f"reject_{pid}"):
        if not reason.strip():
            st.warning("Un motif est obligatoire pour rejeter.")
        else:
            apply_decision(run, lambda: reject(run, pid, reason.strip()))


def reject(run: orch.Run, proposal_id: str, reason: str) -> None:
    alternative = run.reject(proposal_id, reason)
    if alternative is None:
        flash("warning", f"{proposal_id} rejetée : édition manuelle nécessaire.")
    else:
        flash("info", f"{proposal_id} rejetée : alternative {alternative.id} proposée.")


def apply_decision(run: orch.Run, action: Any) -> None:
    """Run a decision of the pipeline; show its refusal, or refresh the page."""
    try:
        action()
    except orch.PipelineError as exc:
        st.error(str(exc))
    else:
        st.rerun()


# --- delivery --------------------------------------------------------------------------------


def delivery_tab(current: ui_state.Project) -> None:
    run = current_run()
    if run is None or run.state.stage in ("indexed", "ops_proposed"):
        st.info("Rien à livrer : la demande n'est pas encore préparée.")
        return
    counts = comp.counts_by_status(run)
    columns = st.columns(len(comp.STATUS_LABELS))
    for column, (status, label) in zip(columns, comp.STATUS_LABELS.items(), strict=True):
        column.metric(label, counts.get(status, 0))
    policy = run.state.version_policy
    st.write(f"Versionnement : **{policy.mode if policy else 'non choisi'}**")
    pending = run.pending_ids()
    if pending:
        st.warning(f"{len(pending)} proposition(s) restent à décider.")
    if run.state.stage == "written":
        st.success("Les DM sont écrits.")
    elif st.button("Écrire les DM", key="write", disabled=not comp.can_write(run)):
        try:
            run.write()
        except orch.PipelineError as exc:
            st.error(str(exc))
        else:
            flash("success", f"DM écrits dans {run.run_dir / 'out'}")
            st.rerun()
    if run.state.stage == "written":
        downloads(run)


def downloads(run: orch.Run) -> None:
    st.subheader("Téléchargements")
    folder = run.run_dir
    st.download_button(
        "DM écrits (zip)", comp.zip_outputs(folder / "out"), file_name=f"{run.state.run_id}.zip",
        mime="application/zip", key="dl_zip",
    )
    files = (
        ("Rapport (HTML)", "report.html", "text/html", "dl_report_html"),
        ("Rapport (JSON)", "report.json", "application/json", "dl_report_json"),
        ("Questions (CSV)", "questions.csv", "text/csv", "dl_questions_csv"),
        ("Décisions (JSONL)", "decisions.jsonl", "application/x-ndjson", "dl_decisions"),
    )
    for label, name, mime, key in files:
        path = folder / name
        if path.is_file():
            st.download_button(label, path.read_bytes(), file_name=name, mime=mime, key=key)
    xlsx = folder / "questions.xlsx"
    if not xlsx.is_file():  # a run resumed from an older write
        export_questions(run.state, xlsx)
    st.download_button(
        "Questions (XLSX)", xlsx.read_bytes(), file_name="questions.xlsx",
        mime=XLSX_MIME, key="dl_questions_xlsx",
    )


# --- assistant -------------------------------------------------------------------------------


def send_message() -> None:
    """Callback of "Envoyer": the reply is built by the assistant (code, or the checked A2)."""
    message = str(st.session_state.get("chat_message", "")).strip()
    if not message:
        return
    history = st.session_state.setdefault(CHAT, [])
    with get_provider(load_config()) as provider:
        reply = answer(message, current_run(), provider)
    history.append(("Vous", message))
    history.append(("Assistant", reply.display))
    st.session_state["chat_message"] = ""


def show_all_proposals() -> None:
    """Callback of "Voir les propositions": list the proposals of every document."""
    st.session_state["only_this_doc"] = False


def assistant_panel() -> None:
    """The right-hand panel: questions about the run, and requests in plain language."""
    st.subheader("Assistant")
    for who, text in st.session_state.get(CHAT, []):
        st.markdown(f"**{who}**\n\n{text}")
    st.text_input("Votre message", key="chat_message")
    typed = str(st.session_state.get("chat_message", "")).strip()
    st.button("Envoyer", key="chat_send", on_click=send_message, disabled=not typed)
    st.button("Voir les propositions", key="chat_see_proposals", on_click=show_all_proposals)
    st.caption("Onglet « Document et propositions » : les propositions à décider.")


# --- page ------------------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="RedacTech", layout="wide")
    st.title("RedacTech")
    sidebar()
    show_flash()
    current = project()
    if current is None:
        return
    main_area, assistant = st.columns([3, 1])
    with main_area:
        request, document, delivery = st.tabs(["Demande", "Document et propositions", "Livraison"])
        with request:
            request_tab(current)
        with document:
            document_tab(current)
        with delivery:
            delivery_tab(current)
    with assistant:
        assistant_panel()


if __name__ == "__main__":
    main()
