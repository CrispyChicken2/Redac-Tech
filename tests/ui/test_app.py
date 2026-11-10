"""End-to-end tests of the Streamlit UI with ``streamlit.testing.v1.AppTest``.

The app is run from its file; the workspace is a copy of the fixtures in ``tmp_path`` (the test
types its path in the sidebar, like a user), and the working directory is ``tmp_path`` so that
the ``runs/`` folder is created there. File uploaders are not driven by AppTest: requests go
through the form, which uses the same pipeline as a mapping table.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from redactech.models import CheckResult
from redactech.sources import workspace as wsmod
from redactech.ui import components as comp
from redactech.ui import state as ui_state

pytestmark = pytest.mark.ui
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402  (after the skip above)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "src" / "redactech" / "ui" / "app.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
FREE = f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML"
COMREP = f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
LRU = (FREE, COMREP, IPD, PROJECT, DEFAULT)
DELETED = "Step marked as deleted but still present."
RUN = "rt_run"
PROJECT_KEY = "rt_project"


# --- helpers ---------------------------------------------------------------------------------


def widget(at: AppTest, kind: str, key: str):
    """The widget of a given kind and key, in the sidebar or in the main area."""
    for root in (at.sidebar, at.main):
        for item in getattr(root, kind):
            if getattr(item, "key", None) == key:
                return item
    raise AssertionError(f"no {kind} with key {key!r}")


def has(at: AppTest, kind: str, key: str) -> bool:
    try:
        widget(at, kind, key)
    except AssertionError:
        return False
    return True


def pick(item, raw: str) -> None:
    """Choose an option of a radio / selectbox: AppTest takes the STORED value, never the label."""
    item.set_value(raw)


def texts(at: AppTest) -> str:
    parts = [m.value for m in at.markdown]
    for kind in ("caption", "info", "success", "warning", "error", "subheader"):
        parts += [e.value for e in getattr(at, kind)]
    return "\n".join(parts)


def workspace_file(tmp_path: Path, names: tuple[str, ...]) -> Path:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(FIXTURES / name, src / name)
    folder = src.resolve()
    source = wsmod.Source("fixtures", folder, [folder], "4.1")
    return wsmod.save_workspace(wsmod.Workspace([source], tmp_path), tmp_path / "ws.toml")


def open_project(tmp_path: Path, monkeypatch, names: tuple[str, ...]) -> AppTest:
    """Start the app and load a project from the fixtures, as a user does."""
    monkeypatch.chdir(tmp_path)
    ws_file = workspace_file(tmp_path, names)
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()
    assert not at.exception
    widget(at, "text_input", "ws_path").set_value(str(ws_file))
    widget(at, "button", "ws_load").click()
    at.run()
    assert not at.exception
    assert PROJECT_KEY in at.session_state
    return at


def fill_form(at: AppTest, values: dict[str, str]) -> None:
    for key, value in values.items():
        widget(at, "text_input", key).set_value(value)
    at.run()


def add_operation(at: AppTest) -> None:
    widget(at, "button", "form_add").click()
    at.run()
    assert not at.exception


def replace_part(at: AppTest, old: str = "LRU1010", new: str = "LRU2020") -> None:
    """Ask for a part replacement through the form and press "Préparer"."""
    pick(widget(at, "radio", "request_mode"), "Formulaire")
    at.run()
    fill_form(at, {"form_replace_part_old": old, "form_replace_part_new": new})
    add_operation(at)
    widget(at, "button", "prepare").click()
    at.run()
    assert not at.exception


def confirm_policy(at: AppTest, mode: str = "in_work") -> None:
    pick(widget(at, "radio", "policy_radio"), mode)
    widget(at, "button", "policy_confirm").click()
    at.run()
    assert not at.exception


def prepared(tmp_path: Path, monkeypatch, mode: str = "in_work") -> AppTest:
    """The LRU1010 -> LRU2020 request, policy confirmed, all proposals listed."""
    at = open_project(tmp_path, monkeypatch, LRU)
    replace_part(at)
    confirm_policy(at, mode)
    widget(at, "checkbox", "only_this_doc").uncheck()
    at.run()
    assert not at.exception
    return at


def run_of(at: AppTest):
    return at.session_state[RUN]


def kinds_of(run):
    zones = {z.id: z for z in run.state.zones}
    certain = [p for p in run.state.proposals
               if zones[p.zone_id].kind == "content" and zones[p.zone_id].certainty == "certain"]
    probable = [p for p in run.state.proposals
                if zones[p.zone_id].kind == "content" and zones[p.zone_id].certainty == "probable"]
    return certain, probable


def decisions(run, proposal_id: str) -> list[dict]:
    return [e for e in run.state.decisions_log
            if e.get("event") == "decision" and e.get("proposal") == proposal_id]


def status_of(run, proposal_id: str) -> str:
    return next(p.status for p in run.state.proposals if p.id == proposal_id)


# --- 1. the versioning choice comes first ----------------------------------------------------


def test_no_proposal_is_listed_until_the_policy_is_confirmed(tmp_path: Path, monkeypatch):
    at = open_project(tmp_path, monkeypatch, LRU)
    replace_part(at)
    run = run_of(at)
    assert run.state.stage == "ops_proposed" and run.state.proposals == []
    assert run.state.version_policy is None
    assert not [e for e in at.expander if e.label.startswith("prop-")]
    assert any("Politique de versionnement" in s.value for s in at.subheader)
    page = texts(at)
    assert "Suggestion" in page and "op-0001" in page  # the suggestion and its reasons
    suggested = run.suggestion().suggested
    assert widget(at, "radio", "policy_radio").value == suggested  # the stored value
    assert not has(at, "button", "write")  # nothing to deliver before the proposals exist


def test_confirming_the_policy_stores_it_and_lists_the_proposals(tmp_path: Path, monkeypatch):
    at = open_project(tmp_path, monkeypatch, LRU)
    replace_part(at)
    confirm_policy(at, "new_issue")
    run = run_of(at)
    assert run.state.version_policy.mode == "new_issue" and run.state.version_policy.reasons
    assert run.state.stage == "proposals_ready" and len(run.state.proposals) >= 3
    assert "Propositions prêtes" in texts(at)
    assert not has(at, "button", "policy_confirm")  # the choice is made


def test_the_default_choice_is_the_suggestion(tmp_path: Path, monkeypatch):
    at = open_project(tmp_path, monkeypatch, LRU)
    replace_part(at)
    suggested = run_of(at).suggestion().suggested
    widget(at, "button", "policy_confirm").click()
    at.run()
    assert run_of(at).state.version_policy.mode == suggested


# --- 2. accept, reject, pending ---------------------------------------------------------------


def test_accepting_updates_the_status_and_the_log(tmp_path: Path, monkeypatch):
    at = prepared(tmp_path, monkeypatch)
    certain, _ = kinds_of(run_of(at))
    target = certain[0].id
    widget(at, "button", f"accept_{target}").click()
    at.run()
    assert not at.exception
    run = run_of(at)
    assert status_of(run, target) == "accepted"
    (entry,) = decisions(run, target)
    assert (entry["status"], entry["actor"]) == ("accepted", "user") and entry["time"]


def test_rejecting_needs_a_reason_then_proposes_an_alternative_or_a_manual_edit(
    tmp_path: Path, monkeypatch
):
    at = prepared(tmp_path, monkeypatch)
    _, probable = kinds_of(run_of(at))
    target = probable[0].id
    widget(at, "button", f"reject_{target}").click()
    at.run()  # no reason: refused
    assert any("motif est obligatoire" in w.value for w in at.warning)
    assert status_of(run_of(at), target) == "proposed" and decisions(run_of(at), target) == []
    widget(at, "text_input", f"reject_reason_{target}").set_value("wrong place")
    widget(at, "button", f"reject_{target}").click()
    at.run()
    assert not at.exception
    run = run_of(at)
    assert status_of(run, target) == "rejected"
    (entry,) = decisions(run, target)
    assert entry["status"] == "rejected" and entry["comment"] == "wrong place"
    # one mention in the text: no alternative, so the writer is told to edit by hand
    assert any("édition manuelle nécessaire" in w.value for w in at.warning)
    assert any(e.get("event") == "needs_manual_edit" for e in run.state.decisions_log)


def test_a_rejection_with_an_alternative_adds_a_proposal(tmp_path: Path, monkeypatch):
    at = open_project(tmp_path, monkeypatch, (PROCED, PROJECT, DEFAULT))
    project = at.session_state[PROJECT_KEY]
    key = next(k for k, name in ui_state.document_choices(project) if name == PROCED)
    pick(widget(at, "radio", "request_mode"), "Formulaire")
    at.run()
    pick(widget(at, "selectbox", "form_kind"), "insert_step")
    at.run()
    pick(widget(at, "selectbox", "form_doc"), key)
    fill_form(at, {"form_target": "stp-0002", "form_insert_step_para": "Check.",
                   "form_insert_step_after_id": "stp-0002"})
    add_operation(at)
    widget(at, "button", "prepare").click()
    at.run()
    confirm_policy(at, "in_work")
    (first,) = run_of(at).state.proposals
    widget(at, "text_input", f"reject_reason_{first.id}").set_value("wrong place")
    widget(at, "button", f"reject_{first.id}").click()
    at.run()
    assert not at.exception
    run = run_of(at)
    alternative = [p for p in run.state.proposals if p.replaces == first.id]
    assert len(alternative) == 1 and status_of(run, first.id) == "rejected"
    assert any(alternative[0].id in i.value for i in at.info)


def test_putting_on_hold_needs_a_comment(tmp_path: Path, monkeypatch):
    at = prepared(tmp_path, monkeypatch)
    certain, _ = kinds_of(run_of(at))
    target = certain[1].id
    widget(at, "button", f"pending_{target}").click()
    at.run()
    assert any("commentaire est obligatoire" in w.value for w in at.warning)
    assert status_of(run_of(at), target) == "proposed"
    widget(at, "text_input", f"pending_comment_{target}").set_value("ask the customer")
    widget(at, "button", f"pending_{target}").click()
    at.run()
    assert not at.exception
    run = run_of(at)
    assert status_of(run, target) == "pending_client"
    proposal = next(p for p in run.state.proposals if p.id == target)
    assert proposal.reviewer_comment == "ask the customer"
    (entry,) = decisions(run, target)
    assert (entry["status"], entry["comment"]) == ("pending_client", "ask the customer")


def test_editing_saves_the_typed_xml(tmp_path: Path, monkeypatch):
    at = prepared(tmp_path, monkeypatch)
    certain, _ = kinds_of(run_of(at))
    target = certain[0]
    typed = target.after_xml
    widget(at, "text_area", f"edit_text_{target.id}").set_value(typed)
    widget(at, "button", f"edit_{target.id}").click()
    at.run()
    assert not at.exception
    run = run_of(at)
    saved = next(p for p in run.state.proposals if p.id == target.id)
    assert saved.status == "edited" and saved.edited_xml == typed


# --- 3. accept all ----------------------------------------------------------------------------


def test_accept_all_accepts_the_certain_ones_and_leaves_the_probable(tmp_path: Path, monkeypatch):
    at = prepared(tmp_path, monkeypatch)
    certain, probable = kinds_of(run_of(at))
    assert len(certain) == 2 and len(probable) == 1
    widget(at, "button", "accept_all").click()
    at.run()
    assert not at.exception
    run = run_of(at)
    assert {status_of(run, p.id) for p in certain} == {"accepted"}
    assert status_of(run, probable[0].id) == "proposed"
    assert "2 acceptée(s) sur 3" in texts(at) and "1 restent à décider" in texts(at)


def test_accept_all_leaves_a_proposal_that_has_an_alert(tmp_path: Path, monkeypatch):
    at = prepared(tmp_path, monkeypatch)
    run = run_of(at)
    certain, _ = kinds_of(run)
    alert = CheckResult(name="links", ok=False, severity="warning", details="x")
    run._replace(certain[0].model_copy(update={"checks": [alert]}))
    widget(at, "button", "accept_all").click()
    at.run()
    assert not at.exception
    assert status_of(run, certain[0].id) == "proposed"
    assert status_of(run, certain[1].id) == "accepted"
    assert "1 acceptée(s) sur 3" in texts(at)


# --- 4. writing ---------------------------------------------------------------------------------


def test_the_write_is_disabled_until_everything_is_decided_then_it_delivers(
    tmp_path: Path, monkeypatch
):
    at = prepared(tmp_path, monkeypatch)
    assert widget(at, "button", "write").disabled is True
    widget(at, "button", "accept_all").click()
    at.run()
    assert widget(at, "button", "write").disabled is True  # the free text is still open
    _, probable = kinds_of(run_of(at))
    widget(at, "button", f"accept_{probable[0].id}").click()
    at.run()
    assert not at.exception
    button = widget(at, "button", "write")
    assert button.disabled is False
    button.click()
    at.run()
    assert not at.exception
    run = run_of(at)
    assert run.state.stage == "written"
    assert any("DM écrits" in s.value for s in at.success)
    labels = {d.proto.label for d in at.get("download_button")}
    assert {"DM écrits (zip)", "Rapport (HTML)", "Rapport (JSON)", "Questions (CSV)",
            "Décisions (JSONL)", "Questions (XLSX)"} <= labels
    for name in ("report.html", "report.json", "questions.csv", "questions.xlsx",
                 "decisions.jsonl"):
        assert (run.run_dir / name).is_file(), name
    assert len(list((run.run_dir / "out").glob("*.XML"))) == 3
    assert not has(at, "button", "write")  # nothing more to write


def test_the_delivery_counts_follow_the_decisions(tmp_path: Path, monkeypatch):
    at = prepared(tmp_path, monkeypatch)
    widget(at, "button", "accept_all").click()
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Acceptée"] == "2" and metrics["À décider"] == "1"


# --- 5. views -------------------------------------------------------------------------------------


def marked_app(tmp_path: Path, monkeypatch) -> AppTest:
    at = open_project(tmp_path, monkeypatch, (MARKED, PROJECT, DEFAULT))
    project = at.session_state[PROJECT_KEY]
    key = next(k for k, name in ui_state.document_choices(project) if name == MARKED)
    pick(widget(at, "selectbox", "doc_select"), key)
    at.run()
    assert not at.exception
    return at


def page_html(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_the_three_views_render(tmp_path: Path, monkeypatch):
    at = marked_app(tmp_path, monkeypatch)
    expected = {
        comp.VIEW_XML: 'class="rt-xml"',
        comp.VIEW_PUBLISHED: 'class="rt-doc"',
        comp.VIEW_BOTH: 'class="rt-side"',
    }
    for view, marker in expected.items():
        widget(at, "radio", "view_mode").set_value(view)
        at.run()
        assert not at.exception, view
        assert marker in page_html(at), view


def test_hiding_the_deletions_hides_the_struck_items(tmp_path: Path, monkeypatch):
    at = marked_app(tmp_path, monkeypatch)
    widget(at, "radio", "view_mode").set_value(comp.VIEW_PUBLISHED)
    at.run()
    assert DELETED in page_html(at) and "rt-deleted" in page_html(at)
    widget(at, "checkbox", "hide_deleted").check()
    at.run()
    assert not at.exception
    assert DELETED not in page_html(at)
    widget(at, "checkbox", "hide_deleted").uncheck()
    at.run()
    assert DELETED in page_html(at)


# --- 6. no automatic acceptance ----------------------------------------


def labels_and_keys(at: AppTest) -> list[str]:
    found: list[str] = []
    kinds = ("button", "checkbox", "radio", "selectbox", "text_input", "text_area",
             "toggle", "multiselect", "slider", "number_input", "file_uploader",
             "download_button")
    for kind in kinds:
        for item in at.get(kind):
            found.append(str(getattr(item, "key", "") or ""))
            found.append(str(getattr(getattr(item, "proto", None), "label", "") or ""))
            found.append(str(getattr(item, "label", "") or ""))
    return found


def test_no_control_exposes_an_automatic_acceptance(tmp_path: Path, monkeypatch):
    at = open_project(tmp_path, monkeypatch, LRU)
    seen = labels_and_keys(at)
    replace_part(at)
    seen += labels_and_keys(at)
    confirm_policy(at)
    seen += labels_and_keys(at)
    widget(at, "button", "accept_all").click()
    at.run()
    seen += labels_and_keys(at)
    assert len(seen) > 30
    assert not [s for s in seen if "auto" in s.lower()], [s for s in seen if "auto" in s.lower()]
    assert run_of(at).request.auto_accept is False
    assert all(e["actor"] == "user" for e in run_of(at).state.decisions_log
               if e.get("event") == "decision")


# --- 7. blocked by a rule ----------------------------------------


def test_a_forbidden_request_is_listed_in_the_blocked_panel(tmp_path: Path, monkeypatch):
    at = open_project(tmp_path, monkeypatch, (PROCED, PROJECT, DEFAULT))
    project = at.session_state[PROJECT_KEY]
    key = next(k for k, name in ui_state.document_choices(project) if name == PROCED)
    pick(widget(at, "radio", "request_mode"), "Formulaire")
    at.run()
    pick(widget(at, "selectbox", "form_kind"), "insert_step")
    at.run()
    pick(widget(at, "selectbox", "form_doc"), key)
    fill_form(at, {"form_target": "stp-0002", "form_insert_step_para": "Check the gauge.",
                   "form_insert_step_after_id": "stp-0002",
                   "form_insert_step_note": "Hot surface"})
    add_operation(at)
    widget(at, "button", "prepare").click()
    at.run()
    confirm_policy(at, "in_work")
    run = run_of(at)
    (blocked,) = [p for p in run.state.proposals if p.status == "blocked_by_rule"]
    assert blocked.attempt == 3
    labels = [e.label for e in at.expander]
    assert "Bloquées par une règle (1)" in labels
    page = texts(at)
    assert blocked.id in page and "règle" in page
    assert "A note is not allowed directly inside a procedural step" in page  # the rule shown
    assert "conflicts with business rule" in page  # the pre-filled question
    assert not [label for label in labels if label.startswith(blocked.id)]  # not a normal card
    widget(at, "button", f"ask_{blocked.id}").click()
    at.run()
    assert not at.exception
    assert status_of(run_of(at), blocked.id) == "pending_client"
    (entry,) = decisions(run_of(at), blocked.id)
    assert entry["status"] == "pending_client" and "business rule" in entry["comment"]


# --- free text ------------------------------------------------------------------------------------

FREE_TEXT_FR = "Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation."
FREE_TEXT_TRAP = "Replace the part LRU1010 by its successor."


def with_recorded_model(tmp_path: Path) -> None:
    """A configuration with the recorded model, and its answers, next to the working directory."""
    (tmp_path / "config.toml").write_text('[llm]\nprovider = "fake"\n', encoding="utf-8")
    shutil.copytree(REPO_ROOT / "tests" / "llm_cassettes", tmp_path / "tests" / "llm_cassettes")


def ask_in_free_text(at: AppTest, text: str) -> None:
    widget(at, "text_area", "free_text").set_value(text)
    at.run()
    widget(at, "button", "prepare_free_text").click()
    at.run()
    assert not at.exception


def test_free_text_says_it_needs_the_local_model_when_none_is_configured(
    tmp_path: Path, monkeypatch
):
    at = open_project(tmp_path, monkeypatch, LRU)  # no config.toml: [llm] provider = "none"
    assert any("modèle local" in i.value for i in at.info)
    assert not has(at, "text_area", "free_text")
    assert not has(at, "button", "prepare_free_text")


def test_free_text_prepares_a_run_when_a_model_is_configured(tmp_path: Path, monkeypatch):
    with_recorded_model(tmp_path)
    at = open_project(tmp_path, monkeypatch, LRU)
    assert not any("modèle local" in i.value for i in at.info)
    assert widget(at, "button", "prepare_free_text").disabled is True  # nothing typed yet
    ask_in_free_text(at, FREE_TEXT_FR)
    run = run_of(at)
    assert run.state.stage == "ops_proposed" and run.state.proposals == []
    (operation,) = run.state.operations
    assert operation.params == {"old": "LRU1010", "new": "LRU2020"}
    assert operation.source[0].doc == "free_text"
    assert run.request.auto_accept is False
    confirm_policy(at, "in_work")  # the same versioning choice, then the same proposals
    assert run_of(at).state.stage == "proposals_ready" and len(run_of(at).state.proposals) >= 3


def test_an_invented_value_is_shown_as_a_question_and_no_operation_exists(
    tmp_path: Path, monkeypatch
):
    with_recorded_model(tmp_path)
    at = open_project(tmp_path, monkeypatch, LRU)
    ask_in_free_text(at, FREE_TEXT_TRAP)
    run = run_of(at)
    assert run.state.operations == []
    assert any("LRU9999" in w.value and "Question" in w.value for w in at.warning)
    confirm_policy(at, "none")
    assert run_of(at).state.proposals == []  # nothing invented reaches a proposal


def test_free_text_is_refused_with_a_message_when_the_model_does_not_know_the_request(
    tmp_path: Path, monkeypatch
):
    with_recorded_model(tmp_path)
    at = open_project(tmp_path, monkeypatch, LRU)
    ask_in_free_text(at, "A request nobody recorded")
    assert RUN not in at.session_state
    assert any("Demande refusée" in e.value for e in at.error)
