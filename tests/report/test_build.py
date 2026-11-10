"""Tests of redactech.report.build: the delivery report of a run."""

from __future__ import annotations

from redactech.report import build


def report_of(state, index, write_result):
    return build.build_report(state, index, write_result)


def test_the_report_identifies_the_run_and_the_policy(state, index, write_result):
    report = report_of(state, index, write_result)
    assert report.run_id == "20250307-140509-ab12" and report.workspace == "C:/work/ws.toml"
    policy = report.version_policy
    assert (policy.mode, policy.suggested) == ("in_work", "new_issue")
    assert policy.reasons == ["op-0001: part -> in_work"] and len(policy.per_doc) == 1


def test_documents_have_old_and_new_names_and_the_policy_applied(state, index, write_result):
    report = report_of(state, index, write_result)
    first, second = report.documents
    assert (first.document, first.old_name) == ("s:DMC-A-520A-A_001-00_EN-US",
                                                "DMC-A-520A-A_001-00_EN-US.XML")
    assert first.new_name == "DMC-A-520A-A_001-01_EN-US.XML" and first.policy == "in_work"
    assert second.new_name == "DMC-B-0A3A-D_001-00_EN-US.XML" and second.policy == "none"


def test_changes_carry_status_comment_excerpts_and_whether_they_were_written(
    state, index, write_result
):
    first, second = report_of(state, index, write_result).documents
    accepted, rejected = first.changes
    assert (accepted.proposal_id, accepted.operation, accepted.change_type) == (
        "p1", "replace_part", "modify")
    assert accepted.status == "accepted" and accepted.comment == "ok" and accepted.written
    assert (accepted.before, accepted.after) == ("<para>old</para>", "<para>new</para>")
    assert rejected.status == "rejected" and not rejected.written and rejected.comment == "no"
    pending, edited = second.changes
    assert pending.status == "pending_client" and not pending.written
    assert edited.status == "edited" and edited.written
    assert edited.after == "<para>typed</para>"  # what the writer typed, not the proposal


def test_checks_are_split_between_pre_existing_and_introduced(state, index, write_result):
    first, second = report_of(state, index, write_result).documents
    (introduced,) = first.introduced
    (old,) = first.pre_existing
    assert (introduced.name, introduced.origin) == ("brex", "introduced")
    assert introduced.rule["id"] == "R-1"
    assert introduced.details == "forbidden <value>" and introduced.xpath == "/dmodule/z1"
    assert (old.name, old.origin, old.details) == ("xsd", "pre_existing", "old problem")
    assert second.introduced == [] and second.pre_existing == []
    assert "illustration" not in {c.name for c in first.introduced + first.pre_existing}


def test_the_same_failure_on_two_proposals_is_listed_once(state, index, write_result):
    twin = state.proposals[0].model_copy(update={"id": "p7", "status": "proposed"})
    state.proposals.append(twin)
    first = report_of(state, index, write_result).documents[0]
    assert len(first.introduced) == 1 and len(first.pre_existing) == 1
    assert [c.proposal_id for c in first.changes] == ["p1", "p5", "p7"]


def test_blocked_requests_show_the_rule_and_the_prefilled_question(
    state, index, write_result, consts
):
    report = report_of(state, index, write_result)
    (blocked,) = report.blocked
    assert (blocked.proposal_id, blocked.operation_id, blocked.attempts) == ("p4", "op-0002", 3)
    assert blocked.rule == consts.rule and blocked.question == consts.question
    assert blocked.document == consts.key_a
    # a blocked proposal is not a change of the document
    assert "p4" not in [c.proposal_id for d in report.documents for c in d.changes]


def test_illustrations_to_check_are_listed_apart(state, index, write_result):
    report = report_of(state, index, write_result)
    (flag,) = report.illustrations
    assert (flag.proposal_id, flag.figure_id, flag.status) == ("p3", "el-z3", "proposed")
    assert flag.reason == "reason of z3" and flag.document == "s:DMC-A-520A-A_001-00_EN-US"
    assert "p3" not in [c.proposal_id for d in report.documents for c in d.changes]


def test_counts_total_the_statuses(state, index, write_result):
    counts = report_of(state, index, write_result).counts
    assert (counts.accepted, counts.edited, counts.rejected) == (1, 1, 1)
    assert (counts.pending_client, counts.blocked, counts.proposed) == (1, 1, 0)
    assert (counts.introduced, counts.pre_existing) == (1, 1)  # the flag is not counted
    state.proposals.append(state.proposals[0].model_copy(update={"id": "p8", "status": "proposed"}))
    assert report_of(state, index, write_result).counts.proposed == 1


def test_pending_blocked_and_operation_questions_are_collected(
    state, index, write_result, consts
):
    questions = report_of(state, index, write_result).questions
    assert [(q.id, q.status) for q in questions] == [
        ("p2", "pending_client"), ("p4", "blocked_by_rule"), ("op-0003", "open")]
    pending, blocked, open_question = questions
    assert pending.text == "Ask the customer <b>?</b>" and pending.element == "el-z2"
    assert pending.document == consts.key_b
    assert blocked.text == consts.question and blocked.rule == "R-1: No <note> here."
    assert open_question.text == "Is the wording right?" and open_question.element == "el-3"


def test_skipped_documents_are_reported(state, index, write_result):
    assert report_of(state, index, write_result).skipped == write_result.skipped


def test_a_report_before_any_write_has_no_new_names(state, index):
    report = build.build_report(state, index, None)
    assert [d.new_name for d in report.documents] == [None, None]
    assert not any(c.written for d in report.documents for c in d.changes)
    assert report.skipped == []


def test_long_excerpts_are_cut():
    text = "x" * (build.EXCERPT + 50)
    cut = build.excerpt(text)
    assert len(cut) == build.EXCERPT + 1 and cut.endswith("…")
    assert build.excerpt("  short  ") == "short" and build.excerpt("") == ""


def test_rule_text():
    assert build.rule_text(None) == ""
    assert build.rule_text({"id": "R", "message": "m"}) == "R: m"
    assert build.rule_text({"id": "R", "xpath": "//x"}) == "R: //x"


def test_the_report_round_trips_through_json(state, index, write_result):
    report = report_of(state, index, write_result)
    assert build.Report.model_validate_json(report.model_dump_json()) == report


# --- check of the delivered files (REQ-11) -------------------------------------------------


def delivered(state, consts, monkeypatch, failures, tmp_path):
    """A write result with two delivered files and a fake A7 returning ``failures`` per file."""
    from types import SimpleNamespace

    from redactech.models import SourceRef

    ref_a = SourceRef(source_id="s", doc_key="DMC-A-520A-A_001-00_EN-US")
    ref_b = SourceRef(source_id="s", doc_key="DMC-B-0A3A-D_001-00_EN-US")
    index = SimpleNamespace(docs={
        consts.key_a: SimpleNamespace(path="a.XML", ref=ref_a),
        consts.key_b: SimpleNamespace(path="b.XML", ref=ref_b),
    })
    files = [tmp_path / "DMC-A-520A-A_001-01_EN-US.XML", tmp_path / "DMC-B-0A3A-D_001-00_EN-US.XML"]
    log = [
        {"doc": consts.key_a, "new_name": files[0].name, "proposals": ["p1"], "policy": "in_work"},
        {"doc": consts.key_b, "new_name": files[1].name, "proposals": ["p6"], "policy": "none"},
    ]
    calls = []

    def fake_check(xdoc, idx, baseline, *, original, ref=None):
        calls.append((xdoc, original.doc_key, ref.doc_key))
        return failures[original.doc_key]

    monkeypatch.setattr(build.a7_checker, "check_doc", fake_check)
    monkeypatch.setattr(build.xio, "load", lambda path: f"doc:{path.name}")
    return index, SimpleNamespace(written=files, log=log, skipped=[]), calls


def test_each_delivered_file_is_checked_and_the_errors_counted(
    state, consts, monkeypatch, tmp_path
):
    from redactech.models import CheckResult

    new_error = CheckResult(name="brex", ok=False, details="x", origin="introduced")
    new_warning = CheckResult(name="icn", ok=False, severity="warning", details="y")
    old = CheckResult(name="xsd", ok=False, details="z", origin="pre_existing")
    failures = {
        "DMC-A-520A-A_001-00_EN-US": [new_error, new_warning, old, old],
        "DMC-B-0A3A-D_001-00_EN-US": [],
    }
    index, result, calls = delivered(state, consts, monkeypatch, failures, tmp_path)
    report = build.build_report(state, index, result)
    first, second = report.outputs
    assert (first.file, first.document) == ("DMC-A-520A-A_001-01_EN-US.XML", consts.key_a)
    assert (first.introduced_errors, first.introduced_warnings, first.pre_existing) == (1, 1, 2)
    assert (second.introduced_errors, second.introduced_warnings, second.pre_existing) == (0, 0, 0)
    assert report.counts.delivered_introduced_errors == 1
    # the file is checked against the baseline of its SOURCE document, under its new name
    assert calls[0] == ("doc:DMC-A-520A-A_001-01_EN-US.XML", "DMC-A-520A-A_001-00_EN-US",
                        "DMC-A-520A-A_001-01_EN-US")


def test_zero_introduced_errors_in_the_delivered_files_is_stated(
    state, consts, monkeypatch, tmp_path
):
    failures = {"DMC-A-520A-A_001-00_EN-US": [], "DMC-B-0A3A-D_001-00_EN-US": []}
    index, result, _ = delivered(state, consts, monkeypatch, failures, tmp_path)
    report = build.build_report(state, index, result)
    assert report.counts.delivered_introduced_errors == 0
    from redactech.report import html

    assert "<b>0 introduced error(s)</b> in the 2 delivered file(s)." in html.render_html(report)


def test_a_file_that_cannot_be_checked_is_reported_not_hidden(
    state, consts, monkeypatch, tmp_path
):
    failures = {"DMC-A-520A-A_001-00_EN-US": [], "DMC-B-0A3A-D_001-00_EN-US": []}
    index, result, _ = delivered(state, consts, monkeypatch, failures, tmp_path)

    def broken(path):
        raise OSError("unreadable")

    monkeypatch.setattr(build.xio, "load", broken)
    first, _ = build.build_report(state, index, result).outputs
    assert first.error == "unreadable"
    index.docs.pop(consts.key_b)
    assert build.build_report(state, index, result).outputs[1].error.startswith("not produced")


def test_nothing_is_checked_without_a_write(state, index):
    report = build.build_report(state, index, None)
    assert report.outputs == [] and report.counts.delivered_introduced_errors is None
