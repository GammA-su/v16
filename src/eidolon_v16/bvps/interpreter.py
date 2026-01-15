from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eidolon_v16.bvps.dsl import (
    Assign,
    BinOp,
    ConstBool,
    ConstInt,
    ConstList,
    Expr,
    If,
    Let,
    ListAppend,
    ListGet,
    ListLen,
    Program,
    Return,
    Var,
    While,
)


@dataclass
class Interpreter:
    step_limit: int = 1000

    def run(self, program: Program, args: list[Any]) -> tuple[Any, dict[str, Any]]:
        env: dict[str, Any] = {}
        for name, value in zip(program.params, args, strict=False):
            env[name] = value
        trace: list[dict[str, Any]] = []
        steps = 0
        output: Any = None

        def record(event: str, payload: dict[str, Any] | None = None) -> None:
            trace.append({"step": steps, "event": event, "payload": payload or {}})

        def eval_expr(expr: Expr) -> Any:
            if isinstance(expr, ConstInt):
                return expr.value
            if isinstance(expr, ConstBool):
                return expr.value
            if isinstance(expr, ConstList):
                return list(expr.value)
            if isinstance(expr, Var):
                return env[expr.name]
            if isinstance(expr, BinOp):
                left = eval_expr(expr.left)
                right = eval_expr(expr.right)
                if expr.op == "add":
                    return int(left) + int(right)
                if expr.op == "sub":
                    return int(left) - int(right)
                if expr.op == "mul":
                    return int(left) * int(right)
                if expr.op == "lt":
                    return int(left) < int(right)
                if expr.op == "lte":
                    return int(left) <= int(right)
                if expr.op == "gt":
                    return int(left) > int(right)
                if expr.op == "eq":
                    return left == right
                raise ValueError("unknown binop")
            if isinstance(expr, ListLen):
                value = eval_expr(expr.value)
                return len(value)
            if isinstance(expr, ListGet):
                value = eval_expr(expr.value)
                index = eval_expr(expr.index)
                return list(value)[int(index)]
            if isinstance(expr, ListAppend):
                value = list(eval_expr(expr.value))
                item = eval_expr(expr.item)
                value.append(int(item))
                return value
            raise ValueError("unknown expr")

        def exec_block(block: list[Any]) -> bool:
            nonlocal steps, output
            for stmt in block:
                steps += 1
                if steps > self.step_limit:
                    raise RuntimeError("step limit exceeded")
                if isinstance(stmt, Let):
                    env[stmt.name] = eval_expr(stmt.expr)
                    record("let", {"name": stmt.name})
                elif isinstance(stmt, Assign):
                    env[stmt.name] = eval_expr(stmt.expr)
                    record("assign", {"name": stmt.name})
                elif isinstance(stmt, If):
                    cond = bool(eval_expr(stmt.cond))
                    record("if", {"cond": cond})
                    if cond:
                        if exec_block(stmt.then_body):
                            return True
                    else:
                        if exec_block(stmt.else_body):
                            return True
                elif isinstance(stmt, While):
                    iterations = 0
                    while bool(eval_expr(stmt.cond)) and iterations < stmt.max_steps:
                        record("while", {"iter": iterations})
                        iterations += 1
                        if exec_block(stmt.body):
                            return True
                elif isinstance(stmt, Return):
                    output = eval_expr(stmt.expr)
                    record("return", {})
                    return True
                else:
                    raise ValueError("unknown statement")
            return False

        exec_block(program.body)
        return output, {"steps": steps, "events": trace}
