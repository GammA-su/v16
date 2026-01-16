from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TriggerSpec(BaseModel):
    task_contains: list[str] = Field(default_factory=list)
    task_family: str | None = None


class SkillImpl(BaseModel):
    kind: Literal["module", "bvps_ast"]
    module_path: str | None = None
    program: dict[str, Any] | None = None
    dsl_version: str | None = None


class SkillSpec(BaseModel):
    name: str
    version: str
    created_ts_utc: str
    origin_episode_id: str
    triggers: TriggerSpec
    io_schema: dict[str, Any] = Field(default_factory=dict)
    preconditions: dict[str, Any] = Field(default_factory=dict)
    verifier_profile: dict[str, Any] = Field(default_factory=dict)
    cost_profile: dict[str, Any] = Field(default_factory=dict)
    impl: SkillImpl
    artifacts: list[str] = Field(default_factory=list)
