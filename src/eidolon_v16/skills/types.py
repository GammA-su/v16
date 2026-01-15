from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SkillSpec(BaseModel):
    skill_id: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    verifiers: list[str] = Field(default_factory=list)
    cost_hint: dict[str, Any] = Field(default_factory=dict)
