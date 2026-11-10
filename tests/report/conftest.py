"""A synthetic run state (no data module is read) shared by the report tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from redactech.models import (
    CheckResult,
    Operation,
    Proposal,
    RunState,
    SourceRef,
    SourceSpan,
    Target,
    VersionPolicy,
    Zone,
)

DOC_A = SourceRef(source_id="s", doc_key="DMC-A-520A-A_001-00_EN-US")
DOC_B = SourceRef(source_id="s", doc_key="DMC-B-0A3A-D_001-00_EN-US")
KEY_A, KEY_B = "s:DMC-A-520A-A_001-00_EN-US", "s:DMC-B-0A3A-D_001-00_EN-US"
RULE = {"id": "R-1", "xpath": "//note", "flag": 0, "message": "No <note> here.", "brex": "b"}
QUESTION = "The request 'add a note' conflicts with business rule R-1: No <note> here. Proceed?"


def operation(number: int, kind: str, ref: SourceRef, questions=()) -> Operation:
    return Operation(
        id=f"op-{number:04d}",
        kind=kind,
        target=Target(ref=ref, element_id=f"el-{number}"),
        params={},
        rationale="why",
        source=[SourceSpan(doc="form", quote="q")],
        questions=list(questions),
    )


def zone(zone_id: str, ref: SourceRef, op_id: str, kind="content", certainty="certain") -> Zone:
    return Zone(
        id=zone_id,
        ref=ref,
        xpath=f"/dmodule/{zone_id}",
        element_id=f"el-{zone_id}",
        certainty=certainty,
        found_by="code",
        kind=kind,
        reason=f"reason of {zone_id}",
        operation_id=op_id,
    )


def proposal(prop_id: str, zone_id: str, ref: SourceRef, op_id: str, **kwargs) -> Proposal:
    values = {
        "id": prop_id,
        "operation_id": op_id,
        "zone_id": zone_id,
        "ref": ref,
        "before_xml": "<para>old</para>",
        "after_xml": "<para>new</para>",
        "change_type": "modify",
    }
    return Proposal(**{**values, **kwargs})


@pytest.fixture
def state() -> RunState:
    introduced = CheckResult(
        name="brex", ok=False, details="forbidden <value>", origin="introduced", rule=RULE,
        xpath="/dmodule/z1",
    )
    old = CheckResult(name="xsd", ok=False, details="old problem", origin="pre_existing")
    flag = CheckResult(name="illustration", ok=False, severity="warning", details="to check")
    return RunState(
        run_id="20250307-140509-ab12",
        workspace="C:/work/ws.toml",
        stage="written",
        version_policy=VersionPolicy(
            mode="in_work", suggested="new_issue", reasons=["op-0001: part -> in_work"],
            per_doc={KEY_B: "none"},
        ),
        operations=[
            operation(1, "replace_part", DOC_A),
            operation(2, "insert_step", DOC_A, [QUESTION]),
            operation(3, "replace_text", DOC_B, ["Is the wording right?"]),
        ],
        zones=[
            zone("z1", DOC_A, "op-0001"),
            zone("z2", DOC_B, "op-0001", certainty="probable"),
            zone("z3", DOC_A, "op-0001", kind="illustration", certainty="to_check"),
            zone("z4", DOC_A, "op-0002"),
            zone("z5", DOC_A, "op-0001"),
            zone("z6", DOC_B, "op-0003"),
        ],
        proposals=[
            proposal("p1", "z1", DOC_A, "op-0001", status="accepted", checks=[introduced, old],
                     reviewer_comment="ok"),
            proposal("p2", "z2", DOC_B, "op-0001", status="pending_client",
                     reviewer_comment="Ask the customer <b>?</b>"),
            proposal("p3", "z3", DOC_A, "op-0001", checks=[flag]),
            proposal("p4", "z4", DOC_A, "op-0002", status="blocked_by_rule", attempt=3,
                     change_type="add", checks=[introduced.model_copy()]),
            proposal("p5", "z5", DOC_A, "op-0001", status="rejected", reviewer_comment="no"),
            proposal("p6", "z6", DOC_B, "op-0003", status="edited",
                     edited_xml="<para>typed</para>"),
        ],
        decisions_log=[
            {"time": "2025-03-07T14:05:09", "event": "ops_proposed"},
            {"time": "2025-03-07T14:06:00", "event": "decision", "proposal": "p1",
             "status": "accepted", "comment": "ok", "actor": "user"},
            {"time": "2025-03-07T14:06:10", "event": "decision", "proposal": "p2",
             "status": "pending_client", "comment": "Ask the customer <b>?</b>", "actor": "user"},
            {"time": "2025-03-07T14:07:00", "event": "written", "files": []},
        ],
    )


@pytest.fixture
def index() -> SimpleNamespace:
    docs = {
        KEY_A: SimpleNamespace(path="C:/src/DMC-A-520A-A_001-00_EN-US.XML"),
        KEY_B: SimpleNamespace(path="C:/src/DMC-B-0A3A-D_001-00_EN-US.XML"),
    }
    return SimpleNamespace(docs=docs)


@pytest.fixture
def write_result() -> SimpleNamespace:
    entry = {
        "doc": KEY_A, "old_name": "DMC-A-520A-A_001-00_EN-US.XML",
        "new_name": "DMC-A-520A-A_001-01_EN-US.XML", "policy": "in_work", "proposals": ["p1"],
        "marks": [],
    }
    other = {
        "doc": KEY_B, "old_name": "DMC-B-0A3A-D_001-00_EN-US.XML",
        "new_name": "DMC-B-0A3A-D_001-00_EN-US.XML", "policy": "none", "proposals": ["p6"],
        "marks": [],
    }
    skipped = [{"proposal": "p9", "reason": "read-only document (upf)"}]
    return SimpleNamespace(written=[], log=[entry, other], skipped=skipped)


@pytest.fixture
def consts() -> SimpleNamespace:
    return SimpleNamespace(key_a=KEY_A, key_b=KEY_B, question=QUESTION, rule=RULE)
