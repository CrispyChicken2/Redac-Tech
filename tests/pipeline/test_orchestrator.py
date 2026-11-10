"""Tests of redactech.pipeline.orchestrator (A0): checkpoints, persistence, decisions, write."""

from __future__ import annotations

import csv
import datetime
import json
import re
import shutil
from pathlib import Path

import pytest

from redactech.models import CheckResult
from redactech.pipeline import orchestrator as orch
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
FREE = f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML"
COMREP = f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
UPF = f"UPF-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
LRU_FILES = (FREE, COMREP, IPD, UPF, PROJECT, DEFAULT)
NOW = datetime.datetime(2025, 3, 7, 14, 5, 9)
TODAY = datetime.date(2025, 3, 7)


class Env:
    """A workspace file over a copy of some fixtures, and a runs folder."""

    def __init__(self, tmp_path: Path, names: tuple[str, ...]):
        self.src = tmp_path / "src"
        self.src.mkdir()
        for name in names:
            shutil.copy(FIXTURES / name, self.src / name)
        folder = self.src.resolve()
        source = wsmod.Source("fixtures", folder, [folder], "4.1")
        self.workspace = wsmod.save_workspace(
            wsmod.Workspace([source], tmp_path), tmp_path / "ws.toml"
        )
        self.runs = tmp_path / "runs"
        self.tmp_path = tmp_path

    def mapping(self, text: str = "old;new;reason\nLRU1010;LRU2020;replaced\n") -> Path:
        path = self.tmp_path / "lots.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def start(self, request: orch.RunRequest, token: str = "ab12") -> orch.Run:
        return orch.start(request, self.workspace, self.runs, clock=lambda: NOW, token=token)

    def lru_run(self, **options) -> orch.Run:
        return self.start(orch.RunRequest(mapping=str(self.mapping()), **options))

    def insert_run(self, params: dict, element_id: str = "stp-0002") -> orch.Run:
        form = {
            "kind": "insert_step",
            "target": {
                "ref": {"source_id": "fixtures", "doc_key": PROCED.removesuffix(".XML")},
                "element_id": element_id,
            },
            "params": params,
            "reason": "requested",
        }
        return self.start(orch.RunRequest(form=form))


def zone_of(run: orch.Run, proposal) -> object:
    return next(z for z in run.state.zones if z.id == proposal.zone_id)


def by_kind(run: orch.Run) -> tuple[list, list]:
    """(certain content proposals, probable content proposals)."""
    certain, probable = [], []
    for p in run.state.proposals:
        zone = zone_of(run, p)
        if zone.kind == "content":
            (certain if zone.certainty == "certain" else probable).append(p)
    return certain, probable


# --- start, request ------------------------------------------------------------


def test_start_indexes_proposes_operations_and_stops_at_the_first_checkpoint(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    assert run.state.stage == "ops_proposed"
    assert run.state.run_id == "20250307-140509-ab12" == run.run_dir.name
    assert [o.kind for o in run.state.operations] == ["replace_part"]
    assert run.state.baseline is not None and run.state.zones == [] and run.state.proposals == []
    assert (run.run_dir / "state.json").is_file() and (run.run_dir / "request.json").is_file()


def test_run_ids_have_a_timestamp_and_four_hex_digits(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    request = orch.RunRequest(mapping=str(env.mapping()))
    run = orch.start(request, env.workspace, env.runs)  # real clock and random token
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", run.state.run_id)


def test_a_request_needs_exactly_one_of_mapping_and_form():
    with pytest.raises(ValueError):
        orch.RunRequest()
    with pytest.raises(ValueError):
        orch.RunRequest(mapping="m.csv", form={"kind": "replace_part"})


def test_the_form_gives_the_operations(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    form = {"kind": "replace_part", "old": "LRU1010", "new": "LRU2020"}
    run = env.start(orch.RunRequest(form=form))
    assert [o.params for o in run.state.operations] == [{"old": "LRU1010", "new": "LRU2020"}]


def test_the_requested_policy_is_stored_with_the_suggestion(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run(version_policy="new_issue")
    policy = run.state.version_policy
    assert policy.mode == "new_issue" and policy.reasons  # the reasons of the suggestion
    other = env.start(orch.RunRequest(mapping=str(env.mapping())), token="cd34")
    assert other.state.version_policy is None


# --- checkpoints ---------------------------------------------------------------


def test_the_pipeline_stops_at_each_checkpoint(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    assert run.state.stage == "ops_proposed"
    run.validate_ops()
    assert run.state.stage == "ops_validated"
    run.propose_zones()
    assert run.state.stage == "zones_proposed" and run.state.zones
    assert run.state.proposals == []  # nothing prepared before the zones are validated
    run.validate_zones()
    assert run.state.stage == "proposals_ready" and run.state.proposals
    stages = ("ops_proposed", "ops_validated", "zones_proposed", "proposals_ready")
    events = [e["event"] for e in run.state.decisions_log if e["event"] in stages]
    assert events == list(stages)


def test_steps_called_out_of_order_are_refused(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    with pytest.raises(orch.PipelineError):
        run.propose_zones()
    with pytest.raises(orch.PipelineError):
        run.decide("p", "accepted")
    with pytest.raises(orch.PipelineError):
        run.write()
    run.validate_ops()
    with pytest.raises(orch.PipelineError):
        run.validate_ops()  # already validated


def test_validate_ops_can_keep_only_some_operations(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.start(orch.RunRequest(mapping=str(env.mapping("old;new\nLRU1010;LRU2020\nX1;X2\n"))))
    assert [o.id for o in run.state.operations] == ["op-0001", "op-0002"]
    with pytest.raises(orch.PipelineError):
        run.validate_ops(["op-0009"])
    run.validate_ops(["op-0001"])
    assert [o.id for o in run.state.operations] == ["op-0001"]
    assert any(e["event"] == "operations_dropped" for e in run.state.decisions_log)


def test_read_only_occurrences_are_logged_and_never_zoned(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    skipped = [e for e in run.state.decisions_log if e["event"] == "skipped_readonly"]
    assert skipped and all("UPF" in e["document"] for e in skipped)
    assert not any("UPF" in z.ref.doc_key for z in run.state.zones)


# --- persistence ---------------------------------------------------------------


def test_the_state_is_saved_after_each_step_and_resumes_exactly(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    for step in (run.validate_ops, run.propose_zones, run.validate_zones):
        step()
        again = orch.load(run.run_dir)
        assert again.state == run.state and again.request == run.request
    resumed = orch.load(run.run_dir)
    certain, _ = by_kind(resumed)
    resumed.decide(certain[0].id, "accepted")
    assert orch.load(run.run_dir).state == resumed.state  # decisions are saved too
    assert "ab12" in (run.run_dir / "state.json").read_text(encoding="utf-8")


def test_a_resumed_run_can_continue_to_write(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    resumed = orch.load(run.run_dir)
    resumed.accept_all()
    resumed.reject(by_kind(resumed)[1][0].id, "not here")
    resumed.set_policy(resumed.suggestion())
    final = orch.load(run.run_dir)
    assert final.write(today=TODAY).written
    assert orch.load(run.run_dir).state.stage == "written"


# --- decisions -----------------------------------------------------------------


def test_nothing_is_written_without_a_decision(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    before = {f.name: f.read_bytes() for f in env.src.iterdir()}
    run = env.lru_run(version_policy="none")
    run.run_to_review()
    with pytest.raises(orch.PipelineError, match="undecided"):
        run.write()
    assert not (run.run_dir / "out").exists()
    run.accept_all()  # the free-text proposal is left: the write is still refused
    with pytest.raises(orch.PipelineError, match="undecided"):
        run.write()
    assert not (run.run_dir / "out").exists()
    assert {f.name: f.read_bytes() for f in env.src.iterdir()} == before  # sources untouched


def test_write_needs_a_chosen_policy(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    run.accept_all()
    run.reject(by_kind(run)[1][0].id)
    with pytest.raises(orch.PipelineError, match="policy"):
        run.write()
    assert not (run.run_dir / "out").exists()


def test_decisions_are_logged_with_time_and_actor(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    certain, probable = by_kind(run)
    run.decide(certain[0].id, "accepted", "ok")
    run.decide(probable[0].id, "pending_client", "ask the customer")
    entries = [e for e in run.state.decisions_log if e["event"] == "decision"]
    assert [(e["proposal"], e["status"], e["comment"], e["actor"]) for e in entries] == [
        (certain[0].id, "accepted", "ok", "user"),
        (probable[0].id, "pending_client", "ask the customer", "user"),
    ]
    assert all(e["time"].startswith("2025-03-07T14:05:09") for e in entries)
    updated = next(p for p in run.state.proposals if p.id == probable[0].id)
    assert updated.status == "pending_client" and updated.reviewer_comment


def test_unknown_decisions_and_proposals_are_refused(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    certain, _ = by_kind(run)
    with pytest.raises(orch.PipelineError, match="unknown proposal"):
        run.decide("nope", "accepted")
    with pytest.raises(orch.PipelineError, match="unknown decision"):
        run.decide(certain[0].id, "maybe")
    with pytest.raises(orch.PipelineError, match="edited XML"):
        run.decide(certain[0].id, "edited")
    assert all(p.status == "proposed" for p in run.state.proposals)


def test_accept_all_is_limited_to_certain_and_clean_proposals(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    certain, probable = by_kind(run)
    assert len(certain) == 2 and len(probable) == 1  # 2 structured changes, 1 free text
    accepted = run.accept_all()
    assert sorted(accepted) == sorted(p.id for p in certain)
    status = {p.id: p.status for p in run.state.proposals}
    assert status[probable[0].id] == "proposed"
    assert run.state.stage == "proposals_ready"  # the free text is still to decide
    assert run.accept_all() == []  # idempotent
    logged = [e for e in run.state.decisions_log if e.get("comment") == "accept-all"]
    assert len(logged) == 2 and {e["actor"] for e in logged} == {"user"}


def test_accept_all_leaves_a_proposal_with_an_introduced_problem(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    first, second = by_kind(run)[0]
    warning = CheckResult(name="links", ok=False, severity="warning", details="x")
    run._replace(first.model_copy(update={"checks": [warning]}))  # introduced: any severity
    old = CheckResult(name="xsd", ok=False, details="old", origin="pre_existing")
    run._replace(second.model_copy(update={"checks": [old]}))  # not the change's fault
    assert run.accept_all() == [second.id]
    assert next(p for p in run.state.proposals if p.id == first.id).status == "proposed"


def test_the_writer_can_not_accept_a_proposal_that_introduces_an_error(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    certain, _ = by_kind(run)
    problem = CheckResult(name="brex", ok=False, details="forbidden")
    run._replace(certain[0].model_copy(update={"checks": [problem]}))
    with pytest.raises(orch.PipelineError, match="introduces errors"):
        run.decide(certain[0].id, "accepted")
    run.decide(certain[0].id, "rejected", "wrong")  # rejecting is always possible


def test_auto_accept_exists_only_when_requested(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    with pytest.raises(orch.PipelineError, match="auto-accept"):
        run.auto_accept()
    auto = env.start(orch.RunRequest(mapping=str(env.mapping()), auto_accept=True), token="cd34")
    auto.run_to_review()
    accepted = auto.auto_accept()
    assert len(accepted) == 2
    actors = {e["actor"] for e in auto.state.decisions_log if e["event"] == "decision"}
    assert actors == {"auto"}


# --- reject -> alternative -----------------------------------------------------


def test_reject_with_a_reason_appends_an_alternative_with_its_derived_operation(tmp_path: Path):
    env = Env(tmp_path, (PROCED, PROJECT, DEFAULT))
    run = env.insert_run({"after_id": "stp-0002", "para": "Check."})
    run.run_to_review()
    (first,) = run.state.proposals
    alternative = run.reject(first.id, "wrong place")
    assert alternative is not None and alternative.replaces == first.id
    assert alternative.attempt == 2 and alternative.rejection_feedback == ["wrong place"]
    assert alternative.status == "proposed" and run.state.stage == "proposals_ready"
    statuses = {p.id: p.status for p in run.state.proposals}
    assert statuses == {first.id: "rejected", alternative.id: "proposed"}
    ids = [o.id for o in run.state.operations]
    assert alternative.operation_id in ids and alternative.operation_id != first.operation_id
    assert [o.id for o in run.base_operations()] == [first.operation_id]
    assert run.suggestion().suggested == "in_work"  # derived operations are not counted twice
    assert [e["alternative"] for e in run.state.decisions_log if e["event"] == "alternative"] == [
        alternative.id
    ]
    # the writer applies the VARIANT: the new step is not where the first proposal put it
    run.decide(alternative.id, "accepted")
    assert run.state.stage == "reviewed"
    run.set_policy(run.suggestion().model_copy(update={"mode": "none"}))
    (path,) = run.write(today=TODAY).written
    assert path.read_text(encoding="utf-8").count("Check.") == 1
    derived = next(o for o in run.state.operations if o.id == alternative.operation_id)
    base = run.base_operations()[0]
    assert derived.params != base.params  # another position: the variant is what was written
    assert "stp-0002" not in str(derived.params.get("after_id", ""))


def test_reject_without_an_alternative_asks_for_a_manual_edit(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    certain, _ = by_kind(run)
    assert run.reject(certain[0].id, "no") is None  # a structured value has no variant
    assert any(e["event"] == "needs_manual_edit" for e in run.state.decisions_log)
    assert next(p for p in run.state.proposals if p.id == certain[0].id).status == "rejected"


def test_rejections_end_after_the_configured_number_of_alternatives(tmp_path: Path):
    env = Env(tmp_path, (PROCED, PROJECT, DEFAULT))
    run = env.insert_run({"after_id": "stp-0002", "para": "Check."})
    run.run_to_review()
    current, produced = run.state.proposals[0], 0
    while True:
        alternative = run.reject(current.id, "again")
        if alternative is None:
            break
        current, produced = alternative, produced + 1
        assert produced <= 5  # never loops
    assert produced == 2  # the two other positions of the new step, then manual edit


# --- blocked_by_rule -----------------------------------------------------------


def test_blocked_proposals_are_never_written(tmp_path: Path):
    env = Env(tmp_path, (PROCED, PROJECT, DEFAULT))
    run = env.insert_run({"after_id": "stp-0002", "para": "Check.", "note": "Hot surface"})
    run.run_to_review()
    (blocked,) = run.state.proposals
    assert blocked.status == "blocked_by_rule" and blocked.attempt == 3
    (question,) = run.state.operations[0].questions
    assert "conflicts with business rule" in question
    with pytest.raises(orch.PipelineError, match="blocked"):
        run.decide(blocked.id, "accepted")
    assert run.accept_all() == []
    run.set_policy(run.suggestion())
    assert run.write(today=TODAY).written == []  # nothing is written for it
    assert not list((run.run_dir / "out").glob("*.XML"))
    assert run.state.stage == "written"


def test_a_blocked_proposal_can_be_sent_to_the_customer(tmp_path: Path):
    env = Env(tmp_path, (PROCED, PROJECT, DEFAULT))
    run = env.insert_run({"after_id": "stp-0002", "para": "Check.", "note": "Hot surface"})
    run.run_to_review()
    (blocked,) = run.state.proposals
    run.decide(blocked.id, "pending_client", "ask about the note rule")
    assert run.state.proposals[0].status == "pending_client"


# --- end to end ----------------------------------------------------------------


def test_lru1010_to_lru2020_end_to_end_with_auto_accept(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run(version_policy="in_work", auto_accept=True)
    run.run_to_review()
    run.auto_accept()
    certain, probable = by_kind(run)
    assert {p.status for p in certain} == {"accepted"}
    assert [p.status for p in probable] == ["proposed"]  # the free-text change is not automatic
    with pytest.raises(orch.PipelineError, match="undecided"):
        run.write()
    run.decide(probable[0].id, "accepted")
    result = run.write(today=TODAY)
    assert run.state.stage == "written" and len(result.written) == 3
    texts = [path.read_text(encoding="utf-8") for path in result.written]
    assert all("LRU2020" in text and "LRU1010" not in text for text in texts)
    assert not any(path.name.startswith("UPF") for path in result.written)  # read-only
    assert (env.src / UPF).read_text(encoding="utf-8").count("LRU1010") == 2  # untouched


def test_the_free_text_change_is_written_only_if_accepted(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run(version_policy="in_work", auto_accept=True)
    run.run_to_review()
    run.auto_accept()
    _, probable = by_kind(run)
    run.reject(probable[0].id, "leave the text")
    result = run.write(today=TODAY)
    assert len(result.written) == 2
    assert not any("-040A-" in path.name for path in result.written)


def test_the_orchestrator_does_not_import_streamlit():
    text = Path(orch.__file__).read_text(encoding="utf-8")
    assert "import streamlit" not in text and "from streamlit" not in text


# --- delivery files ------------------------------------------------------------------------


def test_write_delivers_the_report_the_questions_and_the_decisions(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run(version_policy="in_work", auto_accept=True)
    run.run_to_review()
    run.auto_accept()
    run.decide(by_kind(run)[1][0].id, "accepted", "the wording is fine")
    assert run.delivery_files == []  # nothing before the write
    run.write(today=TODAY)
    assert [p.name for p in run.delivery_files] == [
        "report.json", "report.html", "questions.csv", "decisions.jsonl"]
    assert all(p.parent == run.run_dir and p.is_file() for p in run.delivery_files)
    report = json.loads((run.run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run.state.run_id
    assert report["counts"]["accepted"] == 3 and report["counts"]["blocked"] == 0
    assert len(report["documents"]) == 3
    assert all(d["new_name"].endswith("_001-01_EN-US.XML") for d in report["documents"])
    assert report["version_policy"]["mode"] == "in_work"
    assert len(report["outputs"]) == 3  # the delivered files are checked (REQ-11)
    assert report["counts"]["delivered_introduced_errors"] == 0
    assert all(o["introduced_errors"] == 0 and o["error"] is None for o in report["outputs"])
    assert "<!DOCTYPE html>" in (run.run_dir / "report.html").read_text(encoding="utf-8")
    questions = (run.run_dir / "questions.csv").read_bytes()
    assert questions.decode("utf-8-sig").splitlines() == [
        "id;document;element;question/comment;status;rule"]
    lines = (run.run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and json.loads(lines[-1])["comment"] == "the wording is fine"


def test_a_refused_write_delivers_nothing(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run(version_policy="in_work")
    run.run_to_review()
    with pytest.raises(orch.PipelineError):
        run.write()
    assert run.delivery_files == []
    assert not [f for f in run.run_dir.iterdir() if f.name.startswith(("report", "questions"))]


def test_the_blocked_request_reaches_the_report_and_the_questions(tmp_path: Path):
    env = Env(tmp_path, (PROCED, PROJECT, DEFAULT))
    run = env.insert_run({"after_id": "stp-0002", "para": "Check.", "note": "Hot surface"})
    run.run_to_review()
    run.set_policy(run.suggestion())
    run.write(today=TODAY)
    report = json.loads((run.run_dir / "report.json").read_text(encoding="utf-8"))
    (blocked,) = report["blocked"]
    assert blocked["attempts"] == 3 and blocked["rule"]["xpath"] == "//proceduralStep/note"
    assert "conflicts with business rule" in blocked["question"]
    assert report["counts"]["blocked"] == 1 and report["documents"] == []
    with (run.run_dir / "questions.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[1][4] == "blocked_by_rule" and "business rule" in rows[1][3]
    assert rows[1][5].startswith(blocked["rule"]["id"])


def test_the_flag_rule_and_the_status_counts_come_from_the_run(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run()
    run.run_to_review()
    flags = [p for p in run.state.proposals if run.is_flag(p)]
    zones = {z.id: z for z in run.state.zones}
    assert all(zones[p.zone_id].kind == "illustration" for p in flags)
    content = [p for p in run.state.proposals if not run.is_flag(p)]
    assert run.counts() == {"proposed": len(content)}  # the flags are not counted
    run.decide(content[0].id, "accepted")
    assert run.counts() == {"proposed": len(content) - 1, "accepted": 1}
    assert len(run.pending_ids()) == len(content) - 1


def test_write_also_makes_the_xlsx_of_the_questions(tmp_path: Path):
    env = Env(tmp_path, LRU_FILES)
    run = env.lru_run(version_policy="in_work", auto_accept=True)
    run.run_to_review()
    run.auto_accept()
    run.decide(by_kind(run)[1][0].id, "accepted")
    run.write(today=TODAY)
    assert (run.run_dir / "questions.xlsx").is_file()
    assert "questions.xlsx" not in [p.name for p in run.delivery_files]  # still the four files


# --- free text -------------------------------------------------------------------------

CASSETTES = Path(__file__).resolve().parents[1] / "llm_cassettes"
FR = "Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation."
TRAP = "Replace the part LRU1010 by its successor."


def start_free_text(env: Env, text: str, provider, token: str = "ft01") -> orch.Run:
    request = orch.RunRequest(free_text=text)
    return orch.start(request, env.workspace, env.runs, clock=lambda: NOW, token=token,
                      provider=provider)


def test_a_request_needs_exactly_one_of_mapping_form_and_free_text():
    with pytest.raises(ValueError, match="exactly one"):
        orch.RunRequest(free_text="a", mapping="m.csv")
    with pytest.raises(ValueError, match="exactly one"):
        orch.RunRequest(free_text="a", form={"kind": "replace_part"})
    assert orch.RunRequest(free_text="a").free_text == "a"


def test_a_free_text_request_gives_the_operations_of_the_checked_answer(tmp_path: Path):
    from redactech.llm import FakeLLM

    env = Env(tmp_path, LRU_FILES)
    run = start_free_text(env, FR, FakeLLM(CASSETTES))
    assert run.state.stage == "ops_proposed"
    (operation,) = run.state.operations
    assert operation.kind == "replace_part"
    assert operation.params == {"old": "LRU1010", "new": "LRU2020"}
    assert operation.source[0].doc == "free_text" and operation.source[0].quote in FR
    assert run.free_text_questions() == []
    assert orch.load(run.run_dir).request.free_text == FR  # kept in request.json


def test_a_free_text_run_goes_on_like_any_other(tmp_path: Path):
    from redactech.llm import FakeLLM

    env = Env(tmp_path, LRU_FILES)
    run = start_free_text(env, FR, FakeLLM(CASSETTES))
    run.run_to_review()
    certain, probable = by_kind(run)
    assert len(certain) == 2 and len(probable) == 1  # as with the mapping table
    assert sorted(run.accept_all()) == sorted(p.id for p in certain)


def test_an_invented_value_becomes_a_question_and_no_operation(tmp_path: Path):
    from redactech.llm import FakeLLM

    env = Env(tmp_path, LRU_FILES)
    run = start_free_text(env, TRAP, FakeLLM(CASSETTES))
    assert run.state.operations == []
    (question,) = run.free_text_questions()
    assert "LRU9999" in question
    events = [e for e in run.state.decisions_log if e["event"] == "free_text_question"]
    assert len(events) == 1 and events[0]["time"]
    run.run_to_review()
    assert run.state.proposals == []
    assert orch.load(run.run_dir).free_text_questions() == [question]  # survives a resume


def test_the_questions_reach_the_report_and_the_questions_export(tmp_path: Path):
    from redactech.llm import FakeLLM
    from redactech.report.build import question_entries

    env = Env(tmp_path, LRU_FILES)
    run = start_free_text(env, TRAP, FakeLLM(CASSETTES))
    rows = question_entries(run.state)
    assert [(r.id, r.status) for r in rows] == [("free-text-1", "open")]
    assert "LRU9999" in rows[0].text


def test_without_a_model_a_free_text_request_is_refused_and_leaves_nothing(tmp_path: Path):
    from redactech.llm import NoLLM

    env = Env(tmp_path, LRU_FILES)
    with pytest.raises(orch.PipelineError, match="free text needs the local model"):
        start_free_text(env, FR, NoLLM())
    assert not env.runs.exists() or list(env.runs.iterdir()) == []


def test_the_default_provider_comes_from_the_configuration(tmp_path: Path, monkeypatch):
    env = Env(tmp_path, LRU_FILES)
    monkeypatch.chdir(tmp_path)  # no config.toml here: the defaults, which have no model
    with pytest.raises(orch.PipelineError, match="local model"):
        start_free_text(env, FR, None)


def test_a_missing_cassette_is_a_refusal_not_a_crash(tmp_path: Path):
    from redactech.llm import FakeLLM

    env = Env(tmp_path, LRU_FILES)
    with pytest.raises(orch.PipelineError, match="no cassette"):
        start_free_text(env, "A request nobody recorded", FakeLLM(CASSETTES))
