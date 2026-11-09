"""Round-trip and validation tests of the shared contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from redactech.models import (
    CheckResult,
    Conflict,
    Critique,
    Operation,
    Proposal,
    RunState,
    SourceDoc,
    SourceRef,
    SourceSpan,
    Target,
    VersionPolicy,
    Zone,
)

REF = SourceRef(source_id="fixtures", doc_key="DMC-TEST-A-00-00-00-00A-040A-D")


def _operation() -> Operation:
    return Operation(
        id="op1",
        kind="replace_part",
        target=Target(ref=REF, xpath="//partNumber"),
        params={"old": "X2", "new": "X3"},
        rationale="test",
        source=[SourceSpan(doc="lots.csv", quote="X2 -> X3")],
    )


def _zone() -> Zone:
    return Zone(
        id="z1", ref=REF, xpath="//para", element_id=None, certainty="certain",
        found_by="code", reason="exact match", operation_id="op1",
    )


def _proposal() -> Proposal:
    return Proposal(
        id="p1", operation_id="op1", zone_id="z1", ref=REF,
        before_xml="<a/>", after_xml="<b/>", change_type="modify",
        checks=[CheckResult(name="xsd", ok=True, details="ok")],
        critique=Critique(ok=True),
    )


MODELS = [
    SourceRef(source_id="s", doc_key="k"),
    SourceDoc(ref=REF, brex_chain=[REF], path="a.xml"),
    SourceSpan(doc="d", start=1, end=2, quote="q"),
    Target(ref=REF, xpath="/x", element_id="i"),
    _operation(),
    _zone(),
    CheckResult(name="brex", ok=False, details="d", rule={"id": 1}, ref=REF, xpath="/x"),
    VersionPolicy(mode="in_work", suggested="new_issue", reasons=["r"], per_doc={"k": "none"}),
    Critique(ok=False, doubt="hmm"),
    _proposal(),
    Conflict(id="c1", kind="three_way", description="d", options=[{"a": 1}]),
    RunState(
        run_id="r1", workspace="workspace.toml", stage="indexed", operations=[_operation()],
        zones=[_zone()], proposals=[_proposal()], decisions_log=[{"x": 1}],
    ),
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: type(m).__name__)
def test_round_trip(model):
    cls = type(model)
    assert cls.model_validate(model.model_dump()) == model
    assert cls.model_validate_json(model.model_dump_json()) == model


def test_defaults():
    doc = SourceDoc(ref=REF, path="a.xml")
    assert (doc.kind, doc.role, doc.writable, doc.brex_chain) == ("s1000d", "dm", True, [])
    proposal = _proposal()
    assert proposal.status == "proposed" and proposal.attempt == 1
    assert _operation().confidence == 1.0
    state = RunState(
        run_id="r", workspace="w", stage="written", operations=[], zones=[], proposals=[],
        decisions_log=[],
    )
    assert state.mode == "request" and state.ui_mode == "document" and state.conflicts == []


def test_mutable_defaults_are_not_shared():
    a = SourceDoc(ref=REF, path="a")
    b = SourceDoc(ref=REF, path="b")
    a.brex_chain.append(REF)
    assert b.brex_chain == []


def test_literal_rejection():
    with pytest.raises(ValidationError):
        SourceDoc(ref=REF, path="a", role="nope")
    with pytest.raises(ValidationError):
        Operation(
            id="o", kind="explode", target=Target(), params={}, rationale="r", source=[]
        )
    with pytest.raises(ValidationError):
        CheckResult(name="xsd", ok=True, details="d", origin="elsewhere")
    with pytest.raises(ValidationError):
        VersionPolicy(mode="sometimes", suggested="none")
    with pytest.raises(ValidationError):
        Proposal(
            id="p", operation_id="o", zone_id="z", ref=REF, before_xml="", after_xml="",
            change_type="modify", status="merged",
        )
    with pytest.raises(ValidationError):
        RunState(
            run_id="r", workspace="w", stage="finished", operations=[], zones=[],
            proposals=[], decisions_log=[],
        )


def test_required_fields():
    with pytest.raises(ValidationError):
        SourceRef(source_id="only")
