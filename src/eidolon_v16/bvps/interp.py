from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eidolon_v16.bvps.ast import BinOp, BoolConst, Expr, IfThenElse, IntConst, Program, Var
from eidolon_v16.bvps.types import TypeName, Value


@dataclass(frozen=True)
class EvalTrace:
    steps: int
    events: list[dict[str, Any]]


@dataclass
class Interpreter:
    step_budget: int = 200

    def evaluate(
        self, program: Program, inputs: dict[str, Value], *, trace: bool = False
    ) -> tuple[Value, EvalTrace]:
        env = self._bind_inputs(program, inputs)
        steps = 0
        events: list[dict[str, Any]] = []

        def record(event: str, payload: dict[str, Any]) -> None:
            if trace:
                events.append({"step": steps, "event": event, "payload": payload})

        def tick() -> None:
            nonlocal steps
            steps += 1
            if steps > self.step_budget:
                raise RuntimeError("step budget exceeded")

        def eval_expr(expr: Expr) -> Value:
            tick()
            if isinstance(expr, IntConst):
                record("int", {"value": expr.value})
                return expr.value
            if isinstance(expr, BoolConst):
                record("bool", {"value": expr.value})
                return expr.value
            if isinstance(expr, Var):
                record("var", {"name": expr.name})
                return env[expr.name]
            if isinstance(expr, BinOp):
                left = eval_expr(expr.left)
                right = eval_expr(expr.right)
                record("binop", {"op": expr.op})
                if expr.op == "add":
                    return int(left) + int(right)
                if expr.op == "sub":
                    return int(left) - int(right)
                if expr.op == "mul":
                    return int(left) * int(right)
                if expr.op == "mod":
                    return int(left) % int(right)
                if expr.op == "lt":
                    return int(left) < int(right)
                if expr.op == "gt":
                    return int(left) > int(right)
                if expr.op == "eq":
                    return left == right
                raise ValueError("unknown binop")
            if isinstance(expr, IfThenElse):
                cond = eval_expr(expr.cond)
                record("if", {"cond": bool(cond)})
                if bool(cond):
                    return eval_expr(expr.then_expr)
                return eval_expr(expr.else_expr)
            raise ValueError("unknown expr")

        output = eval_expr(program.body)
        return output, EvalTrace(steps=steps, events=events)

    def _bind_inputs(self, program: Program, inputs: dict[str, Value]) -> dict[str, Value]:
        env: dict[str, Value] = {}
        for name, type_name in program.params:
            if name not in inputs:
                raise ValueError(f"missing input {name}")
            value = inputs[name]
            env[name] = _coerce_value(value, type_name)
        return env


def _coerce_value(value: Value, type_name: TypeName) -> Value:
    if type_name == "Int":
        if isinstance(value, bool):
            raise TypeError("bool is not int")
        return int(value)
    if type_name == "Bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        raise TypeError("invalid bool input")
    raise ValueError(f"unknown type {type_name}")
