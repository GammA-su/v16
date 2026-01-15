from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TypeName = Literal["int", "bool", "list_int"]


class Expr:
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class ConstInt(Expr):
    value: int

    def to_dict(self) -> dict[str, Any]:
        return {"type": "const_int", "value": self.value}


@dataclass(frozen=True)
class ConstBool(Expr):
    value: bool

    def to_dict(self) -> dict[str, Any]:
        return {"type": "const_bool", "value": self.value}


@dataclass(frozen=True)
class ConstList(Expr):
    value: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {"type": "const_list", "value": list(self.value)}


@dataclass(frozen=True)
class Var(Expr):
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "var", "name": self.name}


@dataclass(frozen=True)
class BinOp(Expr):
    op: Literal["add", "sub", "mul", "lt", "lte", "gt", "eq"]
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
class ListLen(Expr):
    value: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "list_len", "value": self.value.to_dict()}


@dataclass(frozen=True)
class ListGet(Expr):
    value: Expr
    index: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "list_get",
            "value": self.value.to_dict(),
            "index": self.index.to_dict(),
        }


@dataclass(frozen=True)
class ListAppend(Expr):
    value: Expr
    item: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "list_append",
            "value": self.value.to_dict(),
            "item": self.item.to_dict(),
        }


class Stmt:
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class Let(Stmt):
    name: str
    expr: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "let", "name": self.name, "expr": self.expr.to_dict()}


@dataclass(frozen=True)
class Assign(Stmt):
    name: str
    expr: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "assign", "name": self.name, "expr": self.expr.to_dict()}


@dataclass(frozen=True)
class If(Stmt):
    cond: Expr
    then_body: list[Stmt]
    else_body: list[Stmt]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "if",
            "cond": self.cond.to_dict(),
            "then": [stmt.to_dict() for stmt in self.then_body],
            "else": [stmt.to_dict() for stmt in self.else_body],
        }


@dataclass(frozen=True)
class While(Stmt):
    cond: Expr
    body: list[Stmt]
    max_steps: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "while",
            "cond": self.cond.to_dict(),
            "body": [stmt.to_dict() for stmt in self.body],
            "max_steps": self.max_steps,
        }


@dataclass(frozen=True)
class Return(Stmt):
    expr: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "return", "expr": self.expr.to_dict()}


@dataclass(frozen=True)
class Program:
    params: list[str]
    body: list[Stmt]
    return_type: TypeName

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": list(self.params),
            "body": [stmt.to_dict() for stmt in self.body],
            "return_type": self.return_type,
        }


def expr_from_dict(payload: dict[str, Any]) -> Expr:
    node_type = payload["type"]
    if node_type == "const_int":
        return ConstInt(value=int(payload["value"]))
    if node_type == "const_bool":
        return ConstBool(value=bool(payload["value"]))
    if node_type == "const_list":
        return ConstList(value=[int(x) for x in payload["value"]])
    if node_type == "var":
        return Var(name=str(payload["name"]))
    if node_type == "binop":
        return BinOp(
            op=payload["op"],
            left=expr_from_dict(payload["left"]),
            right=expr_from_dict(payload["right"]),
        )
    if node_type == "list_len":
        return ListLen(value=expr_from_dict(payload["value"]))
    if node_type == "list_get":
        return ListGet(
            value=expr_from_dict(payload["value"]),
            index=expr_from_dict(payload["index"]),
        )
    if node_type == "list_append":
        return ListAppend(
            value=expr_from_dict(payload["value"]),
            item=expr_from_dict(payload["item"]),
        )
    raise ValueError(f"unknown expr type {node_type}")


def stmt_from_dict(payload: dict[str, Any]) -> Stmt:
    node_type = payload["type"]
    if node_type == "let":
        return Let(name=payload["name"], expr=expr_from_dict(payload["expr"]))
    if node_type == "assign":
        return Assign(name=payload["name"], expr=expr_from_dict(payload["expr"]))
    if node_type == "if":
        return If(
            cond=expr_from_dict(payload["cond"]),
            then_body=[stmt_from_dict(item) for item in payload["then"]],
            else_body=[stmt_from_dict(item) for item in payload["else"]],
        )
    if node_type == "while":
        return While(
            cond=expr_from_dict(payload["cond"]),
            body=[stmt_from_dict(item) for item in payload["body"]],
            max_steps=int(payload["max_steps"]),
        )
    if node_type == "return":
        return Return(expr=expr_from_dict(payload["expr"]))
    raise ValueError(f"unknown stmt type {node_type}")


def program_from_dict(payload: dict[str, Any]) -> Program:
    return Program(
        params=[str(x) for x in payload["params"]],
        body=[stmt_from_dict(item) for item in payload["body"]],
        return_type=payload["return_type"],
    )
