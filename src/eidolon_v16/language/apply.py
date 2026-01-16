from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from eidolon_v16.bvps.ast import (
    BinOp,
    BoolConst,
    Expr,
    IfThenElse,
    IntConst,
    MacroCall,
    Program,
    Var,
    expr_to_str,
)
from eidolon_v16.language.spec import MacroTemplate
from eidolon_v16.ucr.canonical import canonical_json_bytes


@dataclass(frozen=True)
class MacroDefinition:
    params: tuple[str, ...]
    body: Expr


def expand_program(program: Program, macros: Mapping[str, MacroTemplate]) -> Program:
    compiled = {
        name: MacroDefinition(params=tuple(template.params), body=template.to_expr())
        for name, template in macros.items()
    }

    expanded_body = _expand_expr(program.body, compiled)
    return Program(
        params=list(program.params),
        body=expanded_body,
        return_type=program.return_type,
    )


def program_pretty(program: Program) -> str:
    return expr_to_str(program.body)


def program_hash(program: Program) -> str:
    payload = program.to_dict()
    digest = sha256(canonical_json_bytes(payload)).hexdigest()
    return digest


def _expand_expr(expr: Expr, macros: Mapping[str, MacroDefinition]) -> Expr:
    if isinstance(expr, MacroCall):
        macro = macros.get(expr.name)
        if macro is None:
            raise ValueError(f"unknown macro {expr.name}")
        if len(macro.params) != len(expr.args):
            raise ValueError(f"macro {expr.name} expected {len(macro.params)} args")
        arg_map = {
            param: _expand_expr(arg, macros)
            for param, arg in zip(macro.params, expr.args, strict=True)
        }
        substituted = _substitute(macro.body, arg_map)
        return _expand_expr(substituted, macros)
    if isinstance(expr, IntConst):
        return IntConst(value=expr.value)
    if isinstance(expr, BoolConst):
        return BoolConst(value=expr.value)
    if isinstance(expr, Var):
        return Var(name=expr.name)
    if isinstance(expr, BinOp):
        left = _expand_expr(expr.left, macros)
        right = _expand_expr(expr.right, macros)
        return BinOp(op=expr.op, left=left, right=right)
    if isinstance(expr, IfThenElse):
        cond = _expand_expr(expr.cond, macros)
        then_expr = _expand_expr(expr.then_expr, macros)
        else_expr = _expand_expr(expr.else_expr, macros)
        return IfThenElse(cond=cond, then_expr=then_expr, else_expr=else_expr)
    raise ValueError("unknown expr")


def _substitute(expr: Expr, mapping: Mapping[str, Expr]) -> Expr:
    if isinstance(expr, Var) and expr.name in mapping:
        return mapping[expr.name]
    if isinstance(expr, IntConst):
        return IntConst(value=expr.value)
    if isinstance(expr, BoolConst):
        return BoolConst(value=expr.value)
    if isinstance(expr, Var):
        return Var(name=expr.name)
    if isinstance(expr, BinOp):
        left = _substitute(expr.left, mapping)
        right = _substitute(expr.right, mapping)
        return BinOp(op=expr.op, left=left, right=right)
    if isinstance(expr, IfThenElse):
        cond = _substitute(expr.cond, mapping)
        then_expr = _substitute(expr.then_expr, mapping)
        else_expr = _substitute(expr.else_expr, mapping)
        return IfThenElse(cond=cond, then_expr=then_expr, else_expr=else_expr)
    if isinstance(expr, MacroCall):
        expanded_args = tuple(_substitute(arg, mapping) for arg in expr.args)
        return MacroCall(name=expr.name, args=expanded_args)
    raise ValueError("unknown expr")
