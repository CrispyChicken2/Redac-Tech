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
