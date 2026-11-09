"""Tests of redactech.agents.a7_checker (introduced vs pre_existing, veracity)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from redactech.agents import a1_indexer, a4_locator, a5_preparer
from redactech.agents import a7_checker as a7
from redactech.agents.a11_writer import write
from redactech.models import (
    CheckResult,
    Operation,
    Proposal,
    SourceRef,
    SourceSpan,
    Target,
    VersionPolicy,
)
from redactech.s1000d import io as xio
from redactech.sources import workspace as wsmod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "s1000d"
CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
VIOLATING = f"DMC-RTPROTO-{CODE}-521A-A_001-00_EN-US.XML"
PROJECT = f"DMC-RTPROTO-{CODE}-022A-D_001-00_EN-US.XML"
DEFAULT = f"DMC-RTDEFLT-{CODE}-022A-D_001-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"


class Env:
    """A tmp source folder with fixtures, its index and its baseline (A1)."""

    def __init__(self, tmp_path: Path, *names: str):
        self.tmp_path = tmp_path
        self.src = tmp_path / "src"
        self.src.mkdir()
        for name in names:
            shutil.copy(FIXTURES / name, self.src / name)
        folder = self.src.resolve()
        source = wsmod.Source("fixtures", folder, [folder], "4.1")
        self.index, self.baseline = a1_indexer.run(wsmod.Workspace([source], folder))

    def ref(self, name: str) -> SourceRef:
        return SourceRef(source_id="fixtures", doc_key=name.removesuffix(".XML"))

    def xpath_of(self, name: str, expr: str) -> str:
        doc = xio.load(self.src / name)
        element = xio.xpath(doc.root, expr)[0]
        return element.getroottree().getpath(element)

    def propose(self, op: Operation):
        zones = a4_locator.locate(op, self.index).zones
        return zones, a5_preparer.prepare(op, zones, self.index)


def operation(kind: str, params: dict, target: Target | None = None, number: int = 1):
    return Operation(
        id=f"op-{number:04d}",
        kind=kind,
        target=target or Target(),
        params=params,
        rationale=f"reason {number}",
        source=[SourceSpan(doc="form", quote=f"request {number}")],
    )


def failing(results: list[CheckResult], name: str | None = None) -> list[CheckResult]:
    return [r for r in results if not r.ok and (name is None or r.name == name)]


# --- classification -----------------------------------------------------------


def brex_result(rule_id: str = "r1", details: str = "bad", ref: SourceRef | None = None):
    return CheckResult(
        name="brex",
        ok=False,
        details=details,
        rule={"id": rule_id},
        ref=ref or SourceRef(source_id="s", doc_key="d"),
    )


def test_equal_failures_are_matched_one_to_one():
    original = SourceRef(source_id="s", doc_key="d")
    baseline = [brex_result(), brex_result()]
    after = a7.classify([brex_result(), brex_result(), brex_result()], baseline, original)
    assert [r.origin for r in after] == ["pre_existing", "pre_existing", "introduced"]


def test_matching_ignores_line_numbers_and_node_positions():
    original = SourceRef(source_id="s", doc_key="d")
    message = "Element 'x': not expected."
    xsd = CheckResult(name="xsd", ok=False, details=f"line 5: {message}", ref=original)
    moved = xsd.model_copy(update={"details": f"line 9: {message}", "xpath": "/a/b[2]"})
    assert a7.classify([moved], [xsd], original)[0].origin == "pre_existing"
    other = xsd.model_copy(update={"details": "line 9: Element 'y': not expected."})
    assert a7.classify([other], [xsd], original)[0].origin == "introduced"


def test_brex_failures_are_keyed_by_rule_and_message():
    original = SourceRef(source_id="s", doc_key="d")
    baseline = [brex_result("r1", "bad (value 'a')")]
    results = [brex_result("r2", "bad (value 'a')"), brex_result("r1", "bad (value 'b')")]
    assert [r.origin for r in a7.classify(results, baseline, original)] == ["introduced"] * 2


def test_only_the_baseline_of_the_same_document_counts():
    original = SourceRef(source_id="s", doc_key="d")
    elsewhere = brex_result(ref=SourceRef(source_id="s", doc_key="other"))
    assert a7.classify([brex_result()], [elsewhere], original)[0].origin == "introduced"
    ok_result = brex_result().model_copy(update={"ok": True})
    assert a7.classify([brex_result()], [ok_result], original)[0].origin == "introduced"


def test_result_key_shapes():
    assert a7.result_key(brex_result("r9", "m")) == ("brex", "r9", "m")
    xsd = CheckResult(name="xsd", ok=False, details="line 3: msg")
    assert a7.result_key(xsd) == ("xsd", "msg")
    ids = CheckResult(name="ids", ok=False, details="duplicate id 'a'", xpath="/x[2]")
    assert a7.result_key(ids) == ("ids", "duplicate id 'a'")


# --- proposals ----------------------------------------------------------------


def test_pre_existing_errors_stay_pre_existing_when_the_change_is_unrelated(tmp_path: Path):
    env = Env(tmp_path, VIOLATING, PROJECT, DEFAULT)
    assert failing(env.baseline, "brex")  # fixture 9 already violates the project BREX
    where = Target(ref=env.ref(VIOLATING), xpath=env.xpath_of(VIOLATING, "//proceduralStep/para"))
    op = operation("replace_text", {"old": "thing", "new": "task"}, where)
    zones, (proposal,) = env.propose(op)
    results = a7.check_proposal(proposal, env.index, env.baseline, operation=op, zone=zones[0])
    assert results and {r.origin for r in results} == {"pre_existing"}
    assert {r.name for r in results} == {"brex"}


def test_a_change_that_puts_a_note_in_a_step_introduces_a_brex_error(tmp_path: Path):
    env = Env(tmp_path, PROCED, PROJECT, DEFAULT)
    assert failing(env.baseline) == []
    params = {"after_id": "stp-0002", "para": "Check.", "note": "Hot surface"}
    op = operation("insert_step", params, Target(ref=env.ref(PROCED), element_id="stp-0002"))
    zones, (proposal,) = env.propose(op)
    results = a7.check_proposal(proposal, env.index, env.baseline, operation=op, zone=zones[0])
    (error,) = results
    assert (error.name, error.severity, error.origin) == ("brex", "error", "introduced")
    assert error.ok is False
    assert error.rule["xpath"] == "//proceduralStep/note" and error.rule["flag"] == 0
    assert error.xpath and error.xpath.endswith("/note")


def test_a_clean_change_has_no_failure(tmp_path: Path):
    env = Env(tmp_path, PROCED, IPD, PROJECT, DEFAULT)
    op = operation("replace_part", {"old": "X2", "new": "X3"})
    zones, proposals = env.propose(op)
    for zone, proposal in zip(zones, proposals, strict=True):
        assert a7.check_proposal(proposal, env.index, env.baseline, operation=op, zone=zone) == []


def test_an_invented_value_fails_the_veracity_check(tmp_path: Path):
    env = Env(tmp_path, PROCED, PROJECT, DEFAULT)
    op = operation("replace_part", {"old": "X2", "new": "X3"})
    zones, (proposal,) = env.propose(op)
    forged = proposal.model_copy(update={"after_xml": "<partNumber>X7</partNumber>"})
    results = a7.check_proposal(forged, env.index, env.baseline, operation=op, zone=zones[0])
    (error,) = results
    assert (error.name, error.origin, error.severity) == ("veracity", "introduced", "error")
    assert "X7" in error.details
    edited = forged.model_copy(update={"status": "edited", "edited_xml": forged.after_xml})
    assert a7.check_proposal(edited, env.index, env.baseline, operation=op, zone=zones[0]) == []


def test_veracity_accepts_values_from_nested_parameters_and_quotes():
    op = operation("update_ref", {"dm_code": {"infoCode": "520"}, "issue_info": {"inWork": "03"}})
    proposal = Proposal(
        id="p",
        operation_id=op.id,
        zone_id="z",
        ref=SourceRef(source_id="s", doc_key="d"),
        before_xml='<dmCode infoCode="040"/>',
        after_xml='<dmCode infoCode="520" other="request 1"/>',
        change_type="modify",
    )
    assert a7.veracity_failures(proposal, op) == []
    wrong = proposal.model_copy(update={"after_xml": '<dmCode infoCode="999"/>'})
    assert [r.name for r in a7.veracity_failures(wrong, op)] == ["veracity"]


def veracity_proposal(before: str, after: str) -> Proposal:
    return Proposal(
        id="p",
        operation_id="op-0001",
        zone_id="z",
        ref=SourceRef(source_id="s", doc_key="d"),
        before_xml=before,
        after_xml=after,
        change_type="modify",
    )


def test_veracity_compares_whole_tokens_not_substrings():
    op = operation("update_ref", {"quantity": "2"})
    ok = veracity_proposal('<item qty="1"/>', '<item qty="2"/>')
    assert a7.veracity_failures(ok, op) == []
    for invented in ("22", "12", "2 pieces", "Check 2"):
        bad = veracity_proposal('<item qty="1"/>', f'<item qty="{invented}"/>')
        assert [r.name for r in a7.veracity_failures(bad, op)] == ["veracity"], invented


def test_veracity_accepts_the_old_text_with_a_request_substitution():
    op = operation("replace_text", {"old": "LRU1010", "new": "LRU2020"})
    before = "<para>The LRU1010 housing is common.</para>"
    ok = veracity_proposal(before, "<para>The LRU2020 housing is common.</para>")
    assert a7.veracity_failures(ok, op) == []
    bad = veracity_proposal(before, "<para>The LRU2020 housing is red.</para>")
    (error,) = a7.veracity_failures(bad, op)
    assert "red" in error.details


def test_veracity_accepts_a_multi_word_substitution():
    op = operation("replace_text", {"old": "by hand", "new": "with the wrench"})
    before = "<para>Tighten the fasteners by hand.</para>"
    ok = veracity_proposal(before, "<para>Tighten the fasteners with the wrench.</para>")
    assert a7.veracity_failures(ok, op) == []
    bad = veracity_proposal(before, "<para>Tighten the fasteners with the hammer.</para>")
    assert [r.name for r in a7.veracity_failures(bad, op)] == ["veracity"]


def test_generated_ids_and_unchanged_values_are_not_new():
    op = operation("insert_step", {"para": "Check."})
    proposal = Proposal(
        id="p",
        operation_id=op.id,
        zone_id="z",
        ref=SourceRef(source_id="s", doc_key="d"),
        before_xml="",
        after_xml='<proceduralStep id="stp-0006"><para>Check.</para></proceduralStep>',
        change_type="add",
    )
    assert a7.veracity_failures(proposal, op) == []


def test_illustration_zone_gives_only_its_warning(tmp_path: Path):
    env = Env(tmp_path, PROCED, PROJECT, DEFAULT)
    op = operation("replace_part", {"old": "X2", "new": "X3"})
    zones, proposals = env.propose(op)
    flag = zones[0].model_copy(update={"kind": "illustration", "reason": "figure fig-1"})
    (warning,) = a7.check_proposal(proposals[0], env.index, env.baseline, operation=op, zone=flag)
    assert (warning.name, warning.severity, warning.ok) == ("illustration", "warning", False)
    assert warning.details == "to check: figure fig-1"


def test_a_proposal_that_cannot_be_applied_is_an_introduced_error(tmp_path: Path):
    env = Env(tmp_path, PROCED, PROJECT, DEFAULT)
    op = operation("replace_part", {"old": "X2", "new": "X3"})
    zones, (proposal,) = env.propose(op)
    broken = zones[0].model_copy(update={"xpath": "//nothing", "element_id": None})
    (error,) = a7.check_proposal(proposal, env.index, env.baseline, operation=op, zone=broken)
    assert (error.name, error.origin) == ("integrity", "introduced")
    assert "cannot be applied" in error.details


# --- whole output documents ---------------------------------------------------


def written(env: Env, op: Operation):
    zones, proposals = env.propose(op)
    accepted = [p.model_copy(update={"status": "accepted"}) for p in proposals]
    policy = VersionPolicy(mode="in_work", suggested="in_work")
    return write(
        env.tmp_path / "run", env.index, accepted, policy, operations=[op], zones=zones
    ).written


def test_check_doc_of_a_clean_output_is_empty(tmp_path: Path):
    env = Env(tmp_path, PROCED, PROJECT, DEFAULT)
    (path,) = written(env, operation("replace_part", {"old": "X2", "new": "X3"}))
    out = xio.load(path)
    original = env.ref(PROCED)
    assert a7.check_doc(out, env.index, env.baseline, original=original) == []


def test_check_doc_keeps_pre_existing_problems_pre_existing_after_renaming(tmp_path: Path):
    env = Env(tmp_path, VIOLATING, PROJECT, DEFAULT)
    where = Target(ref=env.ref(VIOLATING), xpath=env.xpath_of(VIOLATING, "//proceduralStep/para"))
    (path,) = written(env, operation("replace_text", {"old": "thing", "new": "task"}, where))
    assert path.name != VIOLATING  # the versioning renamed it
    out_ref = SourceRef(source_id="fixtures", doc_key=path.stem)
    results = a7.check_doc(
        xio.load(path), env.index, env.baseline, original=env.ref(VIOLATING), ref=out_ref
    )
    assert results and {r.origin for r in results} == {"pre_existing"}
    assert {r.ref.doc_key for r in results} == {path.stem}


@pytest.mark.parametrize("status", ["proposed", "accepted"])
def test_check_proposal_does_not_change_the_proposal(tmp_path: Path, status: str):
    env = Env(tmp_path, PROCED, PROJECT, DEFAULT)
    op = operation("replace_part", {"old": "X2", "new": "X3"})
    zones, (proposal,) = env.propose(op)
    proposal = proposal.model_copy(update={"status": status})
    before = proposal.model_dump()
    a7.check_proposal(proposal, env.index, env.baseline, operation=op, zone=zones[0])
    assert proposal.model_dump() == before
