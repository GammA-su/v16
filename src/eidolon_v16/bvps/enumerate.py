from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from eidolon_v16.bvps.ast import (
    BinOp,
    BinOpName,
    BoolConst,
    Expr,
    IfThenElse,
    IntConst,
    MacroCall,
    Program,
    Var,
    expr_depth,
    expr_to_str,
)
from eidolon_v16.bvps.types import Spec, TypeName
from eidolon_v16.language.spec import MacroTemplate

INT_OP_ORDER: list[BinOpName] = ["sub", "mod", "add", "mul"]
BOOL_OP_ORDER: list[BinOpName] = ["eq", "lt", "gt"]
COND_OP_ORDER: list[BinOpName] = ["lt", "gt", "eq"]
INT_CONST_ORDER = [0, 1, 2, -1]


def enumerate_programs(
    spec: Spec, macros: dict[str, MacroTemplate] | None = None
) -> Iterator[Program]:
    var_types = {item.name: item.type for item in spec.inputs}
    params = [(item.name, item.type) for item in spec.inputs]
    max_depth = spec.bounds.max_depth
    macros = macros or {}
    for depth in range(max_depth + 1):
        for expr in enumerate_exprs(spec.output, var_types, depth, macros):
            yield Program(params=params, body=expr, return_type=spec.output)


def enumerate_exprs(
    target_type: TypeName,
    var_types: dict[str, TypeName],
    depth: int,
    macros: dict[str, MacroTemplate],
) -> Iterator[Expr]:
    cache: dict[tuple[TypeName, int], list[Expr]] = {}
    yield from _exprs_at_depth(target_type, var_types, depth, cache, macros)


def _exprs_at_depth(
    target_type: TypeName,
    var_types: dict[str, TypeName],
    depth: int,
    cache: dict[tuple[TypeName, int], list[Expr]],
    macros: dict[str, MacroTemplate],
) -> list[Expr]:
    key = (target_type, depth)
    if key in cache:
        return cache[key]
    exprs: list[Expr] = []
    if depth == 0:
        exprs.extend(_base_exprs(target_type, var_types, macros))
        cache[key] = exprs
        return exprs
    if target_type == "Int":
        exprs.extend(_if_exprs(target_type, var_types, depth, cache, macros))
        exprs.extend(_binop_exprs(INT_OP_ORDER, var_types, depth, cache, macros))
    elif target_type == "Bool":
        exprs.extend(_binop_exprs(BOOL_OP_ORDER, var_types, depth, cache, macros))
        exprs.extend(_if_exprs(target_type, var_types, depth, cache, macros))
    else:
        raise ValueError(f"unknown type {target_type}")

    deduped = _dedupe_exprs(exprs)
    cache[key] = deduped
    return deduped


def _base_exprs(
    target_type: TypeName, var_types: dict[str, TypeName], macros: dict[str, MacroTemplate]
) -> list[Expr]:
    constants: list[Expr]
    if target_type == "Int":
        constants = [IntConst(value) for value in INT_CONST_ORDER]
    else:
        constants = [BoolConst(True), BoolConst(False)]
    vars_sorted: list[Expr] = [
        Var(name) for name, typ in sorted(var_types.items()) if typ == target_type
    ]
    macro_calls = _macro_exprs(target_type, var_types, macros)
    return macro_calls + constants + vars_sorted


def _macro_exprs(
    target_type: TypeName,
    var_types: dict[str, TypeName],
    macros: dict[str, MacroTemplate],
) -> list[Expr]:
    exprs: list[Expr] = []
    if target_type not in {"Int", "Bool"}:
        return exprs
    for name, template in macros.items():
        if template.return_type != target_type:
            continue
        params = template.params
        param_types = template.resolved_param_types
        if len(params) != len(param_types):
            continue
        args: list[Expr] = []
        ok = True
        for param_name, expected_type in zip(params, param_types, strict=True):
            var_type = var_types.get(param_name)
            if var_type is None or var_type != expected_type:
                ok = False
                break
            args.append(Var(param_name))
        if not ok:
            continue
        exprs.append(MacroCall(name=name, args=tuple(args)))
    return exprs


def _binop_exprs(
    ops: list[BinOpName],
    var_types: dict[str, TypeName],
    depth: int,
    cache: dict[tuple[TypeName, int], list[Expr]],
    macros: dict[str, MacroTemplate],
) -> list[Expr]:
    exprs: list[Expr] = []
    left_type: TypeName = "Int"
    right_type: TypeName = "Int"
    for op in ops:
        for left_depth, right_depth in _depth_pairs(depth):
            left_exprs = _ordered_exprs(
                _exprs_at_depth(left_type, var_types, left_depth, cache, macros)
            )
            right_exprs = _ordered_exprs(
                _exprs_at_depth(right_type, var_types, right_depth, cache, macros)
            )
            for left in left_exprs:
                for right in right_exprs:
                    exprs.append(BinOp(op=op, left=left, right=right))
    return exprs


def _if_exprs(
    target_type: TypeName,
    var_types: dict[str, TypeName],
    depth: int,
    cache: dict[tuple[TypeName, int], list[Expr]],
    macros: dict[str, MacroTemplate],
) -> list[Expr]:
    exprs: list[Expr] = []
    exprs.extend(_seed_if_exprs(target_type, var_types, depth))
    for cond_depth, then_depth, else_depth in _depth_triples(depth):
        cond_exprs = _filter_cond_exprs(
            _ordered_cond_exprs(
                _exprs_at_depth("Bool", var_types, cond_depth, cache, macros)
            )
        )
        then_exprs = _filter_branch_exprs(
            _ordered_exprs(
                _exprs_at_depth(target_type, var_types, then_depth, cache, macros)
            )
        )
        else_exprs = _filter_branch_exprs(
            _ordered_exprs(
                _exprs_at_depth(target_type, var_types, else_depth, cache, macros)
            )
        )
        for cond in cond_exprs:
            for then_expr in then_exprs:
                for else_expr in else_exprs:
                    exprs.append(
                        IfThenElse(cond=cond, then_expr=then_expr, else_expr=else_expr)
                    )
    return exprs


def _depth_pairs(depth: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for left_depth in range(depth):
        for right_depth in range(depth):
            if max(left_depth, right_depth) != depth - 1:
                continue
            pairs.append((left_depth, right_depth))
    return sorted(
        pairs,
        key=lambda pair: (
            pair[0] + pair[1],
            pair[0] != depth - 1,
            pair[1] != depth - 1,
            pair[0],
            pair[1],
        ),
    )


def _depth_triples(depth: int) -> list[tuple[int, int, int]]:
    triples: list[tuple[int, int, int]] = []
    for cond_depth in range(depth):
        for then_depth in range(depth):
            for else_depth in range(depth):
                if max(cond_depth, then_depth, else_depth) != depth - 1:
                    continue
                triples.append((cond_depth, then_depth, else_depth))
    return sorted(
        triples,
        key=lambda triple: (
            triple[0] + triple[1] + triple[2],
            triple[0] != depth - 1,
            triple[1] != depth - 1,
            triple[2] != depth - 1,
            triple[0],
            triple[1],
            triple[2],
        ),
    )


def _ordered_exprs(exprs: list[Expr]) -> list[Expr]:
    return sorted(exprs, key=_expr_sort_key)


def _ordered_cond_exprs(exprs: list[Expr]) -> list[Expr]:
    return sorted(exprs, key=_cond_sort_key)


def _filter_cond_exprs(exprs: list[Expr]) -> list[Expr]:
    filtered: list[Expr] = []
    for expr in exprs:
        if isinstance(expr, BinOp):
            filtered.append(expr)
    return filtered or exprs


def _filter_branch_exprs(exprs: list[Expr]) -> list[Expr]:
    filtered: list[Expr] = []
    for expr in exprs:
        if not isinstance(expr, IfThenElse):
            filtered.append(expr)
    return filtered or exprs


def _expr_sort_key(expr: Expr) -> tuple[Any, ...]:
    if isinstance(expr, Var):
        return (0, expr.name)
    if isinstance(expr, IntConst):
        return (1, _int_const_rank(expr.value), expr.value)
    if isinstance(expr, BoolConst):
        return (1, 0 if expr.value else 1)
    if isinstance(expr, BinOp):
        op_rank = _op_rank(expr.op, BOOL_OP_ORDER if expr.op in BOOL_OP_ORDER else INT_OP_ORDER)
        return (
            2,
            op_rank,
            _expr_sort_key(expr.left),
            _expr_sort_key(expr.right),
        )
    if isinstance(expr, IfThenElse):
        return (
            3,
            _expr_sort_key(expr.cond),
            _expr_sort_key(expr.then_expr),
            _expr_sort_key(expr.else_expr),
        )
    return (9, expr_to_str(expr))


def _seed_if_exprs(
    target_type: TypeName, var_types: dict[str, TypeName], depth: int
) -> list[Expr]:
    if target_type != "Int":
        return []
    vars_int = [Var(name) for name, typ in sorted(var_types.items()) if typ == "Int"]
    if not vars_int:
        return []
    consts = [IntConst(0), IntConst(1)]
    conds: list[Expr] = []
    for var in vars_int:
        for const in consts:
            conds.append(BinOp("lt", var, const))
            conds.append(BinOp("gt", var, const))
    for left in vars_int:
        for right in vars_int:
            if left.name == right.name:
                continue
            conds.append(BinOp("gt", left, right))
            conds.append(BinOp("lt", left, right))
    branches: list[Expr] = []
    branches.extend(vars_int)
    branches.extend(consts)
    for var in vars_int:
        for const in consts:
            branches.append(BinOp("sub", const, var))
            branches.append(BinOp("sub", var, const))
    exprs: list[Expr] = []
    for cond in conds:
        for then_expr in branches:
            for else_expr in branches:
                candidate = IfThenElse(cond=cond, then_expr=then_expr, else_expr=else_expr)
                if expr_depth(candidate) == depth:
                    exprs.append(candidate)
    return _dedupe_exprs(exprs)


def _cond_sort_key(expr: Expr) -> tuple[Any, ...]:
    if isinstance(expr, BinOp):
        left_kind = _operand_kind(expr.left)
        right_kind = _operand_kind(expr.right)
        pattern_rank = _cond_pattern_rank(left_kind, right_kind)
        op_rank = _op_rank(expr.op, COND_OP_ORDER)
        return (
            0,
            pattern_rank,
            op_rank,
            _operand_sort_key(expr.left),
            _operand_sort_key(expr.right),
        )
    if isinstance(expr, IfThenElse):
        return (2, _expr_sort_key(expr))
    return (1, _expr_sort_key(expr))


def _operand_kind(expr: Expr) -> str:
    if isinstance(expr, Var):
        return "var"
    if isinstance(expr, IntConst):
        return "const"
    return "other"


def _cond_pattern_rank(left_kind: str, right_kind: str) -> int:
    if left_kind == "var" and right_kind == "const":
        return 0
    if left_kind == "var" and right_kind == "var":
        return 1
    if left_kind == "const" and right_kind == "var":
        return 2
    if left_kind == "const" and right_kind == "const":
        return 3
    return 4


def _operand_sort_key(expr: Expr) -> tuple[Any, ...]:
    if isinstance(expr, Var):
        return (0, expr.name)
    if isinstance(expr, IntConst):
        return (1, _int_const_rank(expr.value), expr.value)
    return (2, _expr_sort_key(expr))


def _int_const_rank(value: int) -> int:
    if value in INT_CONST_ORDER:
        return INT_CONST_ORDER.index(value)
    return len(INT_CONST_ORDER) + value


def _op_rank(op: BinOpName, ordering: list[BinOpName]) -> int:
    if op in ordering:
        return ordering.index(op)
    return len(ordering)


def _dedupe_exprs(exprs: list[Expr]) -> list[Expr]:
    seen: set[str] = set()
    ordered: list[Expr] = []
    for expr in exprs:
        key = str(expr.to_dict())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(expr)
    return ordered
