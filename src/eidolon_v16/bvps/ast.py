from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from eidolon_v16.bvps.types import TypeName

BinOpName = Literal["add", "sub", "mul", "mod", "lt", "gt", "eq"]


class Expr:
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class IntConst(Expr):
    value: int

    def to_dict(self) -> dict[str, Any]:
        return {"type": "int_const", "value": self.value}


@dataclass(frozen=True)
class BoolConst(Expr):
    value: bool

    def to_dict(self) -> dict[str, Any]:
        return {"type": "bool_const", "value": self.value}


@dataclass(frozen=True)
class Var(Expr):
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "var", "name": self.name}


@dataclass(frozen=True)
class BinOp(Expr):
    op: BinOpName
    left: Expr
    right: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "binop",
            "op": self.op,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


@dataclass(frozen=True)
class IfThenElse(Expr):
    cond: Expr
    then_expr: Expr
    else_expr: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "if",
            "cond": self.cond.to_dict(),
            "then": self.then_expr.to_dict(),
            "else": self.else_expr.to_dict(),
        }


@dataclass(frozen=True)
class Program:
    params: list[tuple[str, TypeName]]
    body: Expr
    return_type: TypeName

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": [{"name": name, "type": type_name} for name, type_name in self.params],
            "body": self.body.to_dict(),
            "return_type": self.return_type,
        }


@dataclass(frozen=True)
class MacroCall(Expr):
    name: str
    args: tuple[Expr, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "macro",
            "name": self.name,
            "args": [arg.to_dict() for arg in self.args],
        }


def expr_from_dict(payload: dict[str, Any]) -> Expr:
    node_type = payload.get("type")
    if node_type == "int_const":
        return IntConst(value=int(payload["value"]))
    if node_type == "bool_const":
        return BoolConst(value=bool(payload["value"]))
    if node_type == "var":
        return Var(name=str(payload["name"]))
    if node_type == "binop":
        return BinOp(
            op=payload["op"],
            left=expr_from_dict(payload["left"]),
            right=expr_from_dict(payload["right"]),
        )
    if node_type == "if":
        return IfThenElse(
            cond=expr_from_dict(payload["cond"]),
            then_expr=expr_from_dict(payload["then"]),
            else_expr=expr_from_dict(payload["else"]),
        )
    if node_type == "macro":
        args_payload = payload.get("args", [])
        args = tuple(expr_from_dict(arg) for arg in args_payload)
        return MacroCall(name=str(payload["name"]), args=args)
    raise ValueError(f"unknown expr type {node_type}")


def program_from_dict(payload: dict[str, Any]) -> Program:
    params_payload = payload.get("params", [])
    params: list[tuple[str, TypeName]] = []
    for entry in params_payload:
        if not isinstance(entry, dict):
            raise TypeError("program param must be dict")
        name = str(entry.get("name"))
        type_name = _parse_type(entry.get("type"))
        params.append((name, type_name))
    return Program(
        params=params,
        body=expr_from_dict(payload["body"]),
        return_type=_parse_type(payload["return_type"]),
    )


def expr_to_str(expr: Expr) -> str:
    if isinstance(expr, IntConst):
        return str(expr.value)
    if isinstance(expr, BoolConst):
        return "true" if expr.value else "false"
    if isinstance(expr, Var):
        return expr.name
    if isinstance(expr, BinOp):
        return f"({expr_to_str(expr.left)} {expr.op} {expr_to_str(expr.right)})"
    if isinstance(expr, IfThenElse):
        return (
            f"(if {expr_to_str(expr.cond)} then {expr_to_str(expr.then_expr)} "
            f"else {expr_to_str(expr.else_expr)})"
        )
    if isinstance(expr, MacroCall):
        args = ", ".join(expr_to_str(arg) for arg in expr.args)
        return f"{expr.name}({args})"
    raise ValueError("unknown expr")


def expr_depth(expr: Expr) -> int:
    if isinstance(expr, (IntConst, BoolConst, Var)):
        return 0
    if isinstance(expr, BinOp):
        return 1 + max(expr_depth(expr.left), expr_depth(expr.right))
    if isinstance(expr, IfThenElse):
        return 1 + max(
            expr_depth(expr.cond),
            expr_depth(expr.then_expr),
            expr_depth(expr.else_expr),
        )
    if isinstance(expr, MacroCall):
        return 0
    raise ValueError("unknown expr")


def _parse_type(raw: Any) -> TypeName:
    text = str(raw or "").strip()
    if text in {"Int", "int"}:
        return "Int"
    if text in {"Bool", "bool"}:
        return "Bool"
    raise ValueError(f"unknown type {raw}")
