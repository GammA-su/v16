from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from eidolon_v16.bvps.dsl import (
    Assign,
    BinOp,
    ConstBool,
    ConstInt,
    ConstList,
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
from eidolon_v16.bvps.interpreter import Interpreter
from eidolon_v16.ucr.models import TaskInput


@dataclass(frozen=True)
class SynthResult:
    program: Program
    examples: list[dict[str, Any]]
    input_list: list[int]
    operation: str


def synthesize_program(task: TaskInput, seed: int) -> SynthResult:
    normalized = task.normalized
    data = normalized.get("data", {})
    operation = str(data.get("operation", "sum"))
    input_list = [int(x) for x in data.get("input", [1, 2, 3])]
    examples = _normalize_examples(data.get("examples", []), operation)
    rng = random.Random(seed)

    spec = spec_function(operation)
    candidates = _candidate_programs(operation)

    interpreter = Interpreter(step_limit=2000)
    for program in candidates:
        if not _passes_examples(program, examples, spec, interpreter):
            continue
        counterexample = _find_counterexample(program, spec, rng, interpreter)
        if counterexample is None:
            return SynthResult(
                program=program,
                examples=examples,
                input_list=input_list,
                operation=operation,
            )
        examples.append(counterexample)

    fallback = _candidate_programs(operation)[0]
    return SynthResult(
        program=fallback,
        examples=examples,
        input_list=input_list,
        operation=operation,
    )


def spec_function(operation: str) -> Callable[[list[int]], Any]:
    return _spec_function(operation)


def _normalize_examples(examples: list[dict[str, Any]], operation: str) -> list[dict[str, Any]]:
    if examples:
        return examples
    if operation == "sum":
        return [{"input": [1, 2], "output": 3}]
    if operation == "max":
        return [{"input": [1, 5, 2], "output": 5}]
    if operation == "reverse":
        return [{"input": [1, 2], "output": [2, 1]}]
    if operation == "is_sorted":
        return [{"input": [1, 2, 2], "output": True}]
    return []


def _spec_function(operation: str) -> Callable[[list[int]], Any]:
    if operation == "sum":
        return lambda xs: sum(xs)
    if operation == "max":
        return lambda xs: max(xs) if xs else 0
    if operation == "reverse":
        return lambda xs: list(reversed(xs))
    if operation == "is_sorted":
        return lambda xs: all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))
    return lambda xs: None


def _passes_examples(
    program: Program,
    examples: list[dict[str, Any]],
    spec: Callable[[list[int]], Any],
    interpreter: Interpreter,
) -> bool:
    for example in examples:
        inputs = [int(x) for x in example["input"]]
        expected = example.get("output", spec(inputs))
        output, _trace = interpreter.run(program, [inputs])
        if output != expected:
            return False
    return True


def _find_counterexample(
    program: Program,
    spec: Callable[[list[int]], Any],
    rng: random.Random,
    interpreter: Interpreter,
) -> dict[str, Any] | None:
    for _ in range(20):
        length = rng.randint(0, 5)
        sample = [rng.randint(-3, 6) for _ in range(length)]
        expected = spec(sample)
        output, _trace = interpreter.run(program, [sample])
        if output != expected:
            return {"input": sample, "output": expected}
    return None


def _candidate_programs(operation: str) -> list[Program]:
    templates = {
        "sum": [_program_sum(), _program_max(), _program_reverse(), _program_is_sorted()],
        "max": [_program_max(), _program_sum(), _program_reverse(), _program_is_sorted()],
        "reverse": [_program_reverse(), _program_sum(), _program_max(), _program_is_sorted()],
        "is_sorted": [_program_is_sorted(), _program_sum(), _program_max(), _program_reverse()],
    }
    return templates.get(operation, [_program_sum()])


def _program_sum() -> Program:
    xs = Var("xs")
    return Program(
        params=["xs"],
        return_type="int",
        body=[
            Let("total", ConstInt(0)),
            Let("i", ConstInt(0)),
            While(
                cond=BinOp("lt", Var("i"), ListLen(xs)),
                max_steps=100,
                body=[
                    Assign("total", BinOp("add", Var("total"), ListGet(xs, Var("i")))),
                    Assign("i", BinOp("add", Var("i"), ConstInt(1))),
                ],
            ),
            Return(Var("total")),
        ],
    )


def _program_max() -> Program:
    xs = Var("xs")
    return Program(
        params=["xs"],
        return_type="int",
        body=[
            Let("i", ConstInt(0)),
            Let("current", ConstInt(0)),
            If(
                cond=BinOp("gt", ListLen(xs), ConstInt(0)),
                then_body=[Assign("current", ListGet(xs, ConstInt(0)))],
                else_body=[],
            ),
            While(
                cond=BinOp("lt", Var("i"), ListLen(xs)),
                max_steps=100,
                body=[
                    If(
                        cond=BinOp("gt", ListGet(xs, Var("i")), Var("current")),
                        then_body=[Assign("current", ListGet(xs, Var("i")))],
                        else_body=[],
                    ),
                    Assign("i", BinOp("add", Var("i"), ConstInt(1))),
                ],
            ),
            Return(Var("current")),
        ],
    )


def _program_reverse() -> Program:
    xs = Var("xs")
    return Program(
        params=["xs"],
        return_type="list_int",
        body=[
            Let("acc", ConstList([])),
            Let("i", BinOp("sub", ListLen(xs), ConstInt(1))),
            While(
                cond=BinOp("gt", Var("i"), ConstInt(-1)),
                max_steps=100,
                body=[
                    Assign("acc", ListAppend(Var("acc"), ListGet(xs, Var("i")))),
                    Assign("i", BinOp("sub", Var("i"), ConstInt(1))),
                ],
            ),
            Return(Var("acc")),
        ],
    )


def _program_is_sorted() -> Program:
    xs = Var("xs")
    return Program(
        params=["xs"],
        return_type="bool",
        body=[
            Let("i", ConstInt(0)),
            Let("ok", ConstBool(True)),
            While(
                cond=BinOp("lt", Var("i"), BinOp("sub", ListLen(xs), ConstInt(1))),
                max_steps=100,
                body=[
                    If(
                        cond=BinOp(
                            "gt",
                            ListGet(xs, Var("i")),
                            ListGet(xs, BinOp("add", Var("i"), ConstInt(1))),
                        ),
                        then_body=[Assign("ok", ConstBool(False))],
                        else_body=[],
                    ),
                    Assign("i", BinOp("add", Var("i"), ConstInt(1))),
                ],
            ),
            Return(Var("ok")),
        ],
    )
