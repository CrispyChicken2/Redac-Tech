"""Tests of redactech.ui.state and redactech.ui.components (no streamlit needed)."""

from __future__ import annotations

import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from redactech.agents import a1_indexer
from redactech.models import SourceRef
from redactech.pipeline import orchestrator as orch
from redactech.sources import workspace as wsmod
from redactech.ui import components as comp
from redactech.ui import state as ui_state

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
COMREP = f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
FREE = f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML"


def workspace_file(tmp_path: Path, *names: str) -> Path:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(FIXTURES / name, src / name)
    folder = src.resolve()
    source = wsmod.Source("fixtures", folder, [folder], "4.1")
    return wsmod.save_workspace(wsmod.Workspace([source], tmp_path), tmp_path / "ws.toml")


def forbidding_copy(tmp_path: Path, rule: str = "//closeRqmts/reqCondGroup") -> Path:
    """A modified copy of the project BREX (same file name), in another folder."""
    folder = tmp_path / "other_brex"
    folder.mkdir()
    text = (FIXTURES / PROJECT).read_text(encoding="utf-8")
    path = folder / PROJECT
    path.write_text(text.replace("//proceduralStep/note", rule), encoding="utf-8")
    return path


def brex_failures(baseline) -> list:
    return [r for r in baseline if r.name == "brex" and not r.ok and r.severity == "error"]


# --- A1: swapping a BREX ------------------------------------------------------------------


def test_swap_brex_resolves_the_chains_again_and_recomputes_the_baseline(tmp_path: Path):
    ws = wsmod.load_workspace(workspace_file(tmp_path, PROCED, PROJECT, DEFAULT))
    index, baseline = a1_indexer.run(ws)
    assert brex_failures(baseline) == []
    swapped = forbidding_copy(tmp_path)
    after = a1_indexer.swap_brex(ws, index, swapped)
    (failure,) = brex_failures(after)
    assert failure.rule["xpath"] == "//closeRqmts/reqCondGroup"
    assert swapped in index.brex_index["fixtures"].values()
    original = (FIXTURES / PROJECT).read_text(encoding="utf-8")
    assert "//proceduralStep/note" in original  # the fixture is untouched


def test_swap_brex_refuses_a_file_that_is_not_a_brex(tmp_path: Path):
    ws = wsmod.load_workspace(workspace_file(tmp_path, PROCED, PROJECT, DEFAULT))
    index, _ = a1_indexer.run(ws)
    with pytest.raises(ValueError, match="not a BREX"):
        a1_indexer.apply_swap(index, tmp_path / PROCED)


# --- orchestrator: swaps, pending ------------------------------------------------------------


def test_a_run_started_with_a_brex_swap_has_the_new_baseline_and_keeps_it(tmp_path: Path):
    ws_file = workspace_file(tmp_path, PROCED, PROJECT, DEFAULT)
    swapped = forbidding_copy(tmp_path)
    form = {"kind": "replace_text", "params": {"old": "by hand", "new": "with a wrench"},
            "target": {"ref": {"source_id": "fixtures", "doc_key": PROCED.removesuffix(".XML")},
                       "element_id": "stp-0003"}}
    request = orch.RunRequest(form=form, brex_swaps=[str(swapped)])
    run = orch.start(request, ws_file, tmp_path / "runs", token="s001")
    assert len(brex_failures(run.state.baseline)) == 1
    resumed = orch.load(run.run_dir)
    assert resumed.request.brex_swaps == [str(swapped)]
    chain = resumed.index.brex_index["fixtures"]
    assert swapped in chain.values()  # the swap is applied again when the index is rebuilt


def test_pending_ids_lists_what_is_left_to_decide(tmp_path: Path):
    ws_file = workspace_file(tmp_path, FREE, COMREP, IPD, PROJECT, DEFAULT)
    request = orch.RunRequest(form={"kind": "replace_part", "old": "LRU1010", "new": "LRU2020"})
    run = orch.start(request, ws_file, tmp_path / "runs", token="s002")
    run.run_to_review()
    pending = run.pending_ids()
    assert len(pending) == 3
    run.decide(pending[0], "accepted")
    assert run.pending_ids() == pending[1:]


# --- state: project, uploads ------------------------------------------------------------------


def test_default_workspace_path(tmp_path: Path):
    assert ui_state.default_workspace_path(tmp_path) == "workspace.toml"  # nothing there yet
    (tmp_path / "workspace.example.toml").write_text("", encoding="utf-8")
    assert ui_state.default_workspace_path(tmp_path) == "workspace.example.toml"
    (tmp_path / "workspace.toml").write_text("", encoding="utf-8")
    assert ui_state.default_workspace_path(tmp_path) == "workspace.toml"


def test_safe_name_keeps_only_a_plain_file_name():
    assert ui_state.safe_name("a/b/c.XML") == "c.XML"
    assert ui_state.safe_name("..\\..\\evil.xml") == "evil.xml"
    for bad in ("", ".", "..", ".hidden"):
        assert ui_state.safe_name(bad) == ""


def test_the_project_lists_sources_documents_and_the_baseline(tmp_path: Path):
    ws_file = workspace_file(tmp_path, PROCED, PROJECT, DEFAULT, "DMC-RTPROTO-" + CODE
                             + "-521A-A_001-00_EN-US.XML")
    project = ui_state.load_project(ws_file, tmp_path / "session")
    ((source_id, _, writable, roles),) = ui_state.source_rows(project)
    assert (source_id, writable) == ("fixtures", True)
    assert roles["dm"] == 2 and roles["brex"] == 2
    names = [name for _, name in ui_state.document_choices(project)]
    assert PROCED in names and names == sorted(names)
    summary = ui_state.baseline_summary(project)
    assert [d.name for d in summary] == ["DMC-RTPROTO-" + CODE + "-521A-A_001-00_EN-US.XML"]
    assert summary[0].errors >= 1 and len(summary[0].items) >= 1


def test_a_missing_workspace_is_an_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ui_state.load_project(tmp_path / "absent.toml", tmp_path / "s")


def test_uploads_are_saved_classified_and_indexed(tmp_path: Path):
    project = ui_state.load_project(workspace_file(tmp_path, PROJECT, DEFAULT), tmp_path / "s")
    before = project.workspace_file
    data = (FIXTURES / PROCED).read_bytes()
    results = ui_state.add_uploads(project, [(PROCED, data), ("../../evil.xml", b"<a/>"),
                                             ("", b"x"), ("pic.png", b"png")])
    saved = {u.name: u.role for u in results if u.saved}
    assert saved[PROCED] == "dm" and "evil.xml" in saved and "pic.png" in saved
    assert [u.problem for u in results if not u.saved] == ["invalid file name"]
    assert (project.uploads_dir / PROCED).read_bytes() == data
    assert not (tmp_path / "evil.xml").exists()  # never outside the uploads folder
    assert project.workspace_file != before and project.workspace_file.is_file()
    rows = {row[0]: row for row in ui_state.source_rows(project)}
    assert "uploads" in rows and rows["uploads"][3].get("dm") == 1
    assert any(PROCED == name for _, name in ui_state.document_choices(project))
    assert (tmp_path / "ws.toml").read_text(encoding="utf-8").count("[[sources]]") == 1


def test_uploading_nothing_valid_changes_nothing(tmp_path: Path):
    project = ui_state.load_project(workspace_file(tmp_path, PROJECT, DEFAULT), tmp_path / "s")
    results = ui_state.add_uploads(project, [("", b"x")])
    assert not results[0].saved and project.uploads == []
    assert project.workspace_file == project.base_file


def test_swapping_a_brex_from_the_ui(tmp_path: Path):
    project = ui_state.load_project(workspace_file(tmp_path, PROCED, PROJECT, DEFAULT),
                                    tmp_path / "s")
    assert brex_failures(project.baseline) == []
    data = forbidding_copy(tmp_path).read_bytes()
    path = ui_state.swap_project_brex(project, PROJECT, data)
    assert path.parent == project.session_dir / "brex_swap" and project.brex_swaps == [path]
    assert len(brex_failures(project.baseline)) == 1
    summary = ui_state.baseline_summary(project)
    assert [d.name for d in summary] == [PROCED]
    with pytest.raises(ValueError):
        ui_state.swap_project_brex(project, PROCED, b"<dmodule/>")
    assert project.brex_swaps == [path]
    assert not (project.session_dir / "brex_swap" / PROCED).exists()
    with pytest.raises(ValueError, match="invalid"):
        ui_state.swap_project_brex(project, "..", b"")


def test_the_swap_survives_new_uploads(tmp_path: Path):
    project = ui_state.load_project(workspace_file(tmp_path, PROCED, PROJECT, DEFAULT),
                                    tmp_path / "s")
    ui_state.swap_project_brex(project, PROJECT, forbidding_copy(tmp_path).read_bytes())
    ui_state.add_uploads(project, [("note.txt", b"x")])
    assert len(brex_failures(project.baseline)) == 1


# --- state: runs ------------------------------------------------------------------------------


def lru_project(tmp_path: Path) -> ui_state.Project:
    ws_file = workspace_file(tmp_path, FREE, COMREP, IPD, PROJECT, DEFAULT)
    return ui_state.load_project(ws_file, tmp_path / "s")


def test_a_mapping_starts_a_run_without_proposals_and_without_auto_accept(tmp_path: Path):
    project = lru_project(tmp_path)
    run = ui_state.start_run(project, mapping=("lots.csv", b"old;new\nLRU1010;LRU2020\n"),
                             runs_dir=tmp_path / "runs")
    assert run.state.stage == "ops_proposed" and run.state.proposals == []
    assert run.state.version_policy is None  # to be chosen first
    assert run.request.auto_accept is False
    assert (project.session_dir / "requests" / "lots.csv").is_file()


def test_the_policy_is_stored_then_the_proposals_are_prepared(tmp_path: Path):
    project = lru_project(tmp_path)
    run = ui_state.start_run(project, mapping=("lots.csv", b"old;new\nLRU1010;LRU2020\n"),
                             runs_dir=tmp_path / "runs")
    ui_state.confirm_policy(run, "new_issue")
    assert run.state.version_policy.mode == "new_issue" and run.state.version_policy.reasons
    assert run.state.stage == "proposals_ready" and len(run.state.proposals) >= 3
    with pytest.raises(ValueError):
        ui_state.confirm_policy(run, "whenever")


def test_forms_start_a_run_and_nothing_starts_without_a_request(tmp_path: Path):
    project = lru_project(tmp_path)
    form = comp.build_form("replace_part", None, {"old": "LRU1010", "new": "LRU2020"})
    run = ui_state.start_run(project, forms=[form], runs_dir=tmp_path / "runs")
    assert [o.kind for o in run.state.operations] == ["replace_part"]
    with pytest.raises(ValueError):
        ui_state.start_run(project, runs_dir=tmp_path / "runs")


def test_highlight_ids_are_the_elements_of_the_proposals_of_one_document(tmp_path: Path):
    ws_file = workspace_file(tmp_path, PROCED, PROJECT, DEFAULT)
    project = ui_state.load_project(ws_file, tmp_path / "s")
    key = next(k for k, name in ui_state.document_choices(project) if name == PROCED)
    form = comp.build_form("replace_text", ui_state.doc_ref(project, key),
                           {"old": "by hand", "new": "with a wrench"}, target="stp-0003")
    run = ui_state.start_run(project, forms=[form], runs_dir=tmp_path / "runs")
    ui_state.confirm_policy(run, "in_work")
    assert ui_state.highlight_ids(run, key) == ["stp-0003"]
    assert ui_state.highlight_ids(run, "nope") == []


# --- components -------------------------------------------------------------------------------


def test_badges_distinguish_pre_existing_introduced_and_illustration():
    from redactech.models import CheckResult, Proposal, Zone

    ref = SourceRef(source_id="s", doc_key="d")
    checks = [
        CheckResult(name="brex", ok=False, details="x", origin="introduced"),
        CheckResult(name="xsd", ok=False, details="y", origin="pre_existing"),
        CheckResult(name="brex", ok=False, details="z", origin="introduced"),
        CheckResult(name="icn", ok=True, severity="info", details="fine"),
        CheckResult(name="illustration", ok=False, severity="warning", details="to check"),
    ]
    proposal = Proposal(id="p", operation_id="o", zone_id="z", ref=ref, before_xml="",
                        after_xml="", change_type="add", checks=checks)
    zone = Zone(id="z", ref=ref, xpath="/x", element_id=None, certainty="to_check",
                found_by="code", kind="illustration", reason="r", operation_id="o")
    found = comp.badges(proposal, zone)
    assert [b.kind for b in found] == ["illustration", "introduced", "pre_existing"]
    html = comp.badges_html(proposal, zone)
    assert 'rt-badge-introduced">Introduit : brex<' in html and "rt-badge-pre_existing" in html
    assert comp.badge_html(comp.Badge("<b>", "introduced")).count("<b>") == 0


def test_form_fields_follow_the_operation_requirements():
    names = {k: [f.name for f in comp.form_fields(k)] for k in comp.form_kinds()}
    assert names["replace_part"] == ["old", "new"]
    assert names["insert_step"] == ["para", "after_id", "before_id", "note"]
    assert [f.required for f in comp.form_fields("insert_step")] == [True, False, False, False]
    assert "dm_code" in names["update_ref"] and "internal_ref_id" in names["update_ref"]
    assert set(names) == set(comp.KIND_LABELS)


def test_build_form_makes_what_the_pipeline_reads():
    from redactech.agents.a2_mapping import from_form

    ref = SourceRef(source_id="s", doc_key="d")
    form = comp.build_form("insert_step", ref, {"para": "Go.", "after_id": " stp-1 ", "note": ""},
                           target="stp-1", reason=" why ")
    assert form == {"kind": "insert_step", "params": {"para": "Go.", "after_id": "stp-1"},
                    "reason": "why", "target": {"ref": ref.model_dump(), "element_id": "stp-1"}}
    (operation,) = from_form(form)
    assert operation.target.ref == ref and operation.rationale == "why"
    xpath = comp.build_form("update_ref", ref, {"internal_ref_id": "a"}, target="//x/y")
    assert xpath["target"]["xpath"] == "//x/y" and "element_id" not in xpath["target"]
    json_form = comp.build_form("update_ref", ref, {"dm_code": '{"infoCode": "520"}'})
    assert json_form["params"]["dm_code"] == {"infoCode": "520"}
    with pytest.raises(ValueError):
        comp.build_form("update_ref", ref, {"dm_code": "{oops"})
    plain = comp.build_form("replace_part", ref, {"old": "A", "new": "B"})
    assert "target" not in plain  # a part replacement is located by the pipeline
    assert "Remplacer" in comp.describe_form(plain) and "old=A" in comp.describe_form(plain)


def test_counts_and_the_write_condition(tmp_path: Path):
    project = lru_project(tmp_path)
    run = ui_state.start_run(project, mapping=("lots.csv", b"old;new\nLRU1010;LRU2020\n"),
                             runs_dir=tmp_path / "runs")
    assert not comp.can_decide(run) and not comp.can_write(run)
    ui_state.confirm_policy(run, "in_work")
    assert comp.can_decide(run) and not comp.can_write(run)  # proposals still to decide
    counts = comp.counts_by_status(run)
    assert counts["proposed"] == len(run.pending_ids())
    for proposal_id in run.pending_ids():
        run.decide(proposal_id, "accepted")
    assert comp.can_write(run)
    run.write()
    assert not comp.can_decide(run) and not comp.can_write(run)
    assert comp.counts_by_status(run)["accepted"] >= 3
    assert comp.status_label("pending_client") == "En attente du client"
    assert comp.status_label("odd") == "odd"


def test_the_zip_holds_the_written_modules(tmp_path: Path):
    project = lru_project(tmp_path)
    run = ui_state.start_run(project, mapping=("lots.csv", b"old;new\nLRU1010;LRU2020\n"),
                             runs_dir=tmp_path / "runs")
    ui_state.confirm_policy(run, "in_work")
    run.accept_all()
    for proposal_id in run.pending_ids():
        run.decide(proposal_id, "accepted")
    run.write()
    with zipfile.ZipFile(BytesIO(comp.zip_outputs(run.run_dir / "out"))) as archive:
        names = archive.namelist()
    assert len(names) == 3 and all(n.endswith(".XML") for n in names)
    assert comp.zip_outputs(tmp_path / "absent") != b"" and zipfile.is_zipfile(
        BytesIO(comp.zip_outputs(tmp_path / "absent")))
