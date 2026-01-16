from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any


def safe_eval_int(expr: str) -> int:
    node = ast.parse(expr, mode="eval")
    return int(_eval_node(node.body))


Number = float | int


def safe_eval_arith(expr: str) -> Number:
    node = ast.parse(expr, mode="eval")
    return _eval_arith_node(node.body)


def _eval_node(node: ast.AST) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return int(node.value)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        ops: dict[type[ast.AST], Any] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.FloorDiv: operator.floordiv,
            ast.Div: operator.floordiv,
            ast.Mod: operator.mod,
        }
        op_type = type(node.op)
        if op_type not in ops:
            raise ValueError("unsupported op")
        return int(ops[op_type](left, right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand)
    raise ValueError("unsupported expression")


def _eval_arith_node(node: ast.AST) -> Number:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("unsupported literal")
        return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_arith_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _eval_arith_node(node.left)
        right = _eval_arith_node(node.right)
        ops: dict[type[ast.AST], Callable[[Number, Number], Number]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        op_type = type(node.op)
        if op_type not in ops:
            raise ValueError("unsupported op")
        return ops[op_type](left, right)
    raise ValueError("unsupported expression")
