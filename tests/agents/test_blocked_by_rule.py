"""Tests of the BREX retry loop and the blocked_by_rule status (A5 + A7)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from redactech.agents import a1_indexer, a4_locator, a5_preparer
from redactech.agents import a7_checker as a7
from redactech.models import CheckResult, Operation, SourceRef, SourceSpan, Target
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
RULE_XPATH = "//proceduralStep/note"
RULE_TEXT = "A note is not allowed directly inside a procedural step"
QUOTE = "add a step with a hot surface note"


class Env:
    def __init__(self, tmp_path: Path, project_rule: str | None = None):
        self.src = tmp_path / "src"
        self.src.mkdir()
        for name in (PROCED, PROJECT, DEFAULT):
            shutil.copy(FIXTURES / name, self.src / name)
        if project_rule is not None:  # a custom project rule instead of the note rule
            path = self.src / PROJECT
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(RULE_XPATH, project_rule), encoding="utf-8")
        folder = self.src.resolve()
        source = wsmod.Source("fixtures", folder, [folder], "4.1")
        self.index, self.baseline = a1_indexer.run(wsmod.Workspace([source], folder))

    def insert(self, params: dict, element_id: str) -> tuple[Operation, list]:
        ref = SourceRef(source_id="fixtures", doc_key=PROCED.removesuffix(".XML"))
        op = Operation(
            id="op-0001",
            kind="insert_step",
            target=Target(ref=ref, element_id=element_id),
            params=params,
            rationale="requested",
            source=[SourceSpan(doc="form", quote=QUOTE)],
        )
        return op, a4_locator.locate(op, self.index).zones


NOTE_STEP = {"after_id": "stp-0002", "para": "Check.", "note": "Hot surface"}


@pytest.fixture
def counted(monkeypatch):
    """Count the calls of the checker made by the retry loop."""
    calls = []
    real = a7.check_proposal

    def counting(*args, **kwargs):
        calls.append(args[0].id)
        return real(*args, **kwargs)

    monkeypatch.setattr(a5_preparer.a7_checker, "check_proposal", counting)
    return calls


# --- blocked ------------------------------------------------------------------


def test_a_step_that_needs_a_forbidden_note_is_blocked_after_three_attempts(
    tmp_path: Path, counted: list[str]
):
    env = Env(tmp_path)
    op, zones = env.insert(NOTE_STEP, "stp-0002")
    checked = a5_preparer.prepare_checked(op, zones, env.index, env.baseline)
    (proposal,) = checked.proposals
    assert proposal.status == "blocked_by_rule"
    assert proposal.attempt == 3 and len(counted) == 3  # 1 try + 2 retries, then it stops
    (error,) = [c for c in proposal.checks if c.name == "brex" and not c.ok]
    assert error.origin == "introduced" and error.rule["xpath"] == RULE_XPATH
    assert error.rule["flag"] == 0 and RULE_TEXT in error.rule["message"]
    assert len(proposal.rejection_feedback) == 2
    assert all(error.rule["id"] in note for note in proposal.rejection_feedback)


def test_the_customer_question_is_prefilled_on_the_operation(tmp_path: Path):
    env = Env(tmp_path)
    op, zones = env.insert(NOTE_STEP, "stp-0002")
    checked = a5_preparer.prepare_checked(op, zones, env.index, env.baseline)
    (proposal,) = checked.proposals
    rule = next(c.rule for c in proposal.checks if c.name == "brex")
    assert checked.operation.questions == [
        f"The request '{QUOTE}' conflicts with business rule {rule['id']}: {RULE_TEXT}. "
        "How should we proceed?"
    ]
    assert op.questions == []  # the given operation is not modified
    again = a5_preparer.prepare_checked(checked.operation, zones, env.index, env.baseline)
    assert len(again.operation.questions) == 1  # the same question is not added twice


@pytest.mark.parametrize("retries,attempts", [(0, 1), (1, 2), (2, 3), (9, 3)])
def test_attempts_are_counted_and_capped(tmp_path: Path, counted, retries: int, attempts: int):
    env = Env(tmp_path)
    op, zones = env.insert(NOTE_STEP, "stp-0002")
    checked = a5_preparer.prepare_checked(
        op, zones, env.index, env.baseline, max_rule_retries=retries
    )
    assert checked.proposals[0].status == "blocked_by_rule"
    assert checked.proposals[0].attempt == attempts and len(counted) == attempts
    # at most 3 attempts because only two code alternatives exist for this insertion
    assert len(counted) <= 1 + retries


def test_with_a_single_alternative_there_are_two_attempts(tmp_path: Path, counted):
    env = Env(tmp_path)
    params = {"after_id": "stp-0005", "para": "Last.", "note": "Hot"}
    op, zones = env.insert(params, "stp-0005")
    (proposal,) = a5_preparer.prepare_checked(op, zones, env.index, env.baseline).proposals
    # after the last step: only "before it" remains as alternative (the next step does not exist)
    assert proposal.status == "blocked_by_rule" and proposal.attempt == 2 and len(counted) == 2


# --- not blocked --------------------------------------------------------------


def test_a_clean_proposal_is_left_alone(tmp_path: Path, counted):
    env = Env(tmp_path)
    op, zones = env.insert({"after_id": "stp-0002", "para": "Check."}, "stp-0002")
    checked = a5_preparer.prepare_checked(op, zones, env.index, env.baseline)
    (proposal,) = checked.proposals
    assert proposal.status == "proposed" and proposal.attempt == 1 and proposal.checks == []
    assert checked.operation.questions == [] and len(counted) == 1


def test_an_alternative_without_the_failure_replaces_the_proposal(tmp_path: Path):
    """The rule forbids the new step right after stp-0002: the next position is fine."""
    forbidden = "//proceduralStep[@id='stp-0002']/following-sibling::*[1][@id='stp-0006']"
    env = Env(tmp_path, project_rule=forbidden)
    assert not [r for r in env.baseline if not r.ok]
    op, zones = env.insert({"after_id": "stp-0002", "para": "Check."}, "stp-0002")
    (first,) = a5_preparer.prepare(op, zones, env.index)
    assert a7.check_proposal(first, env.index, env.baseline, operation=op, zone=zones[0])
    checked = a5_preparer.prepare_checked(op, zones, env.index, env.baseline)
    (proposal,) = checked.proposals
    assert proposal.status == "proposed" and proposal.attempt == 2
    assert proposal.replaces == first.id
    assert not [c for c in proposal.checks if c.name == "brex" and not c.ok]
    assert checked.operation.questions == []


def test_failures_on_different_rules_do_not_block(tmp_path: Path, monkeypatch):
    env = Env(tmp_path)
    op, zones = env.insert(NOTE_STEP, "stp-0002")
    calls = []

    def varying(proposal, index, baseline, *, operation, zone):
        calls.append(proposal.id)
        return [
            CheckResult(
                name="brex",
                ok=False,
                severity="error",
                details="bad",
                origin="introduced",
                rule={"id": f"rule-{len(calls)}", "message": "m"},
                ref=proposal.ref,
            )
        ]

    monkeypatch.setattr(a5_preparer.a7_checker, "check_proposal", varying)
    checked = a5_preparer.prepare_checked(op, zones, env.index, env.baseline)
    (proposal,) = checked.proposals
    assert proposal.status == "proposed" and proposal.attempt == 1
    assert len(calls) == 3 and checked.operation.questions == []


def test_pre_existing_brex_errors_never_trigger_the_loop(tmp_path: Path, monkeypatch):
    env = Env(tmp_path)
    op, zones = env.insert({"after_id": "stp-0002", "para": "Check."}, "stp-0002")
    calls = []

    def inherited(proposal, index, baseline, *, operation, zone):
        calls.append(proposal.id)
        return [
            CheckResult(
                name="brex", ok=False, details="old", origin="pre_existing", rule={"id": "r"},
                ref=proposal.ref,
            )
        ]

    monkeypatch.setattr(a5_preparer.a7_checker, "check_proposal", inherited)
    (proposal,) = a5_preparer.prepare_checked(op, zones, env.index, env.baseline).proposals
    assert proposal.status == "proposed" and len(calls) == 1


# --- question text and alternatives cap ---------------------------------------


def test_customer_question_text():
    op = Operation(
        id="o", kind="insert_step", target=Target(), params={}, rationale="why", source=[]
    )
    rule = {"id": "R-7", "message": "No notes here."}
    assert a5_preparer.customer_question(op, rule) == (
        "The request 'why' conflicts with business rule R-7: No notes here. How should we proceed?"
    )
    with_quote = op.model_copy(update={"source": [SourceSpan(doc="d", quote="q")]})
    assert "The request 'q' conflicts" in a5_preparer.customer_question(with_quote, rule)
    fallback = a5_preparer.customer_question(op, {"id": "R-9", "xpath": "//x"})
    assert "business rule R-9: //x." in fallback


@pytest.mark.parametrize("cap,expected", [(1, 1), (2, 2), (3, 2)])
def test_rejections_return_at_most_max_alternatives(tmp_path: Path, cap: int, expected: int):
    env = Env(tmp_path)
    op, zones = env.insert({"after_id": "stp-0002", "para": "Check."}, "stp-0002")
    (current,) = a5_preparer.prepare(op, zones, env.index)
    produced = 0
    while True:
        alternatives = a5_preparer.prepare(
            op, zones, env.index, a5_preparer.Rejection(current), max_alternatives=cap
        )
        if not alternatives:
            break
        (current,) = alternatives
        produced += 1
        assert produced <= 5  # never loops
    assert produced == expected
