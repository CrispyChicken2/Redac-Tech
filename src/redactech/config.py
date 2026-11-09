"""Configuration loader (SPEC section 10): config.toml, with defaults when absent."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "none"
    model: str = "ministral-3:8b"
    temperature: float = 0
    max_retries: int = 2
    timeout_s: int = 120


class TraceConfig(BaseModel):
    delete_mode: str = "mark"
    consolidate_on_new_issue: bool = True
    default_version_policy: str = "ask"
    marks_when_none: bool = True
    upf_policy: str = "read_only"
    max_alternatives: int = 3
    max_rule_retries: int = 2


class WorkspaceConfig(BaseModel):
    file: str = "workspace.toml"


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    trace: TraceConfig = Field(default_factory=TraceConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)


def load_config(path: Path | None = None) -> Config:
    """Load ``path`` (default: config.toml in the current directory); defaults if missing."""
    target = Path(path) if path is not None else Path("config.toml")
    if not target.is_file():
        return Config()
    with target.open("rb") as fh:
        data = tomllib.load(fh)
    return Config.model_validate(data)
