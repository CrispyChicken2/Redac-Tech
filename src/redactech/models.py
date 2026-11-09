"""Shared pydantic data contracts (SPEC section 9), owned by the ORCH."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourceRef(BaseModel):
    source_id: str
    doc_key: str


class SourceDoc(BaseModel):
    ref: SourceRef
    kind: Literal["s1000d", "xml", "graphic", "other"] = "s1000d"
    role: Literal["dm", "brex", "icn", "pm", "ddn", "upf", "other"] = "dm"
    issue: str | None = None
    language: str | None = None
    brex_chain: list[SourceRef] = []
    writable: bool = True
    path: str


class SourceSpan(BaseModel):
    doc: str
    start: int | None = None
    end: int | None = None
    quote: str


class Target(BaseModel):
    ref: SourceRef | None = None
    xpath: str | None = None
    element_id: str | None = None


class Operation(BaseModel):
    id: str
    kind: Literal[
        "replace_part",
        "replace_text",
        "insert_step",
        "delete_step",
        "move_step",
        "update_ref",
        "add_requirement",
        "remove_requirement",
        "update_applic",
        "update_value",
        "write_steps",
        "fix_violation",
        "translate_dm",
    ]
    target: Target
    params: dict
    rationale: str
    source: list[SourceSpan]
    confidence: float = 1.0
    questions: list[str] = []


class Zone(BaseModel):
    id: str
    ref: SourceRef
    xpath: str
    element_id: str | None
    certainty: Literal["certain", "probable", "to_check"]
    found_by: Literal["code", "llm", "user"]
    kind: Literal["content", "illustration"] = "content"
    reason: str
    operation_id: str


class CheckResult(BaseModel):
    name: Literal[
        "xsd",
        "brex",
        "integrity",
        "links",
        "ids",
        "veracity",
        "applic",
        "icn",
        "illustration",
        "writing_standard",
    ]
    ok: bool
    severity: Literal["error", "warning", "info"] = "error"
    details: str
    origin: Literal["pre_existing", "introduced"] = "introduced"
    rule: dict | None = None
    ref: SourceRef | None = None
    xpath: str | None = None


class VersionPolicy(BaseModel):
    mode: Literal["none", "in_work", "new_issue"]
    suggested: Literal["none", "in_work", "new_issue"]
    reasons: list[str] = []
    per_doc: dict[str, Literal["none", "in_work", "new_issue"]] = {}


class Critique(BaseModel):
    ok: bool
    doubt: str | None = None


class Proposal(BaseModel):
    id: str
    operation_id: str
    zone_id: str
    ref: SourceRef
    before_xml: str
    after_xml: str
    change_type: Literal["add", "modify", "delete"]
    checks: list[CheckResult] = []
    critique: Critique | None = None
    status: Literal[
        "proposed", "accepted", "edited", "rejected", "pending_client", "blocked_by_rule"
    ] = "proposed"
    reviewer_comment: str | None = None
    edited_xml: str | None = None
    attempt: int = 1
    rejection_feedback: list[str] = []
    replaces: str | None = None


class Conflict(BaseModel):
    id: str
    kind: Literal["three_way", "cross_document"]
    description: str
    options: list[dict]
    chosen: str | None = None
    status: Literal["open", "resolved", "pending_client"] = "open"
    client_comment: str | None = None


class RunState(BaseModel):
    run_id: str
    mode: Literal["request", "compare"] = "request"
    workspace: str
    version_policy: VersionPolicy | None = None
    baseline: list[CheckResult] = []
    ui_mode: Literal["document", "guided"] = "document"
    stage: Literal[
        "indexed",
        "ops_proposed",
        "ops_validated",
        "zones_proposed",
        "zones_validated",
        "proposals_ready",
        "reviewed",
        "written",
    ]
    operations: list[Operation]
    zones: list[Zone]
    proposals: list[Proposal]
    conflicts: list[Conflict] = []
    decisions_log: list[dict]
