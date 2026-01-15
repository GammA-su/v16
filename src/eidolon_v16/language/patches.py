from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ScopeConstraint(BaseModel):
    scope: str
    details: dict[str, Any] = Field(default_factory=dict)


class ConservativityClaim(BaseModel):
    claim: str
    proof_stub: str | None = None
    bounded_scope: str | None = None


class RollbackPlan(BaseModel):
    steps: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)


class LanguagePatch(BaseModel):
    patch_id: str
    kind: Literal["macro", "rewrite", "type", "cost_model"]
    scope: ScopeConstraint
    conservativity: ConservativityClaim
    rollback: RollbackPlan

    @field_validator("conservativity")
    @classmethod
    def _require_conservativity(cls, value: ConservativityClaim) -> ConservativityClaim:
        if not value.claim:
            raise ValueError("conservativity claim required")
        if not (value.proof_stub or value.bounded_scope):
            raise ValueError("must provide proof_stub or bounded_scope")
        return value
