from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from eidolon_v16.bvps.types import TypeName

if TYPE_CHECKING:
    from eidolon_v16.bvps.ast import Expr
    from eidolon_v16.bvps.types import TypeName


class MacroTemplate(BaseModel):
    params: list[str] = Field(default_factory=list)
    param_types: Sequence[TypeName] | None = None
    return_type: TypeName = "Int"
    body: dict[str, Any]

    @property
    def resolved_param_types(self) -> list[TypeName]:
        if self.param_types:
            return list(self.param_types)
        return ["Int"] * len(self.params)

    def to_expr(self) -> Expr:
        from eidolon_v16.bvps.ast import expr_from_dict

        return expr_from_dict(self.body)


class PatchSpec(BaseModel):
    name: str
    version: str
    created_ts_utc: str
    scope: str
    macros: dict[str, MacroTemplate] = Field(default_factory=dict)
    proof_kind: Literal["definitional"] = "definitional"
    description: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    preconditions: dict[str, Any] = Field(default_factory=dict)
