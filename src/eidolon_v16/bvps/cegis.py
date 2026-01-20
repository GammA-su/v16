from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import enumerate as bvps_enumerate
from eidolon_v16.bvps.interp import Interpreter
from eidolon_v16.bvps.types import Example, Spec, TypeName, Value, spec_from_dict
from eidolon_v16.language.apply import expand_program
from eidolon_v16.language.spec import MacroTemplate


@dataclass(frozen=True)
class SynthesisStats:
    candidates_tried: int
    depth: int
    counterexamples: int
    seed: int
    fuzz_trials: int


@dataclass(frozen=True)
class SynthesisResult:
    program: bvps_ast.Program
    examples: list[Example]
    counterexamples: list[Example]
    stats: SynthesisStats
    macros_enabled: bool
    profile: "SynthesisProfile"
    fastpath: bool = False


@dataclass(frozen=True)
class SynthesisProfile:
    enum_ms: int
    eval_ms: int
    cegis_ms: int
    total_ms: int
    depth_max: int
    cegis_iters: int


def synthesize(
    spec: Spec,
    seed: int | None = None,
    *,
    macros: dict[str, MacroTemplate] | None = None,
) -> SynthesisResult:
    total_start = time.perf_counter()
    rng_seed = _resolve_seed(spec, seed)
    interpreter = Interpreter(step_budget=spec.bounds.step_budget)
    examples = _prepare_examples(spec, interpreter)
    oracle_expr = _parse_oracle(spec)
    counterexamples: list[Example] = []
    candidates_tried = 0
    depth_used = 0
    depth_max = 0
    macros = macros or {}
    enum_ms = 0.0
    eval_ms = 0.0
    cegis_ms = 0.0

    iterator = iter(bvps_enumerate.enumerate_programs(spec, macros=macros))
    while True:
        enum_start = time.perf_counter()
        try:
            candidate = next(iterator)
        except StopIteration:
            break
        enum_ms += time.perf_counter() - enum_start
        candidates_tried += 1
        depth_used = bvps_ast.expr_depth(candidate.body)
        if depth_used > depth_max:
            depth_max = depth_used
        program = expand_program(candidate, macros)
        eval_start = time.perf_counter()
        passes = _passes_examples(program, examples, interpreter, oracle_expr, spec)
        eval_ms += time.perf_counter() - eval_start
        if not passes:
            if candidates_tried >= spec.bounds.max_programs:
                break
            continue
        cegis_start = time.perf_counter()
        counterexample = fuzz_counterexample(program, spec, rng_seed, oracle_expr)
        cegis_ms += time.perf_counter() - cegis_start
        if counterexample is not None:
            examples.append(counterexample)
            counterexamples.append(counterexample)
            if candidates_tried >= spec.bounds.max_programs:
                break
            continue
        stats = SynthesisStats(
            candidates_tried=candidates_tried,
            depth=depth_used,
            counterexamples=len(counterexamples),
            seed=rng_seed,
            fuzz_trials=spec.bounds.fuzz_trials,
        )
        total_ms = int((time.perf_counter() - total_start) * 1000)
        profile = SynthesisProfile(
            enum_ms=int(enum_ms * 1000),
            eval_ms=int(eval_ms * 1000),
            cegis_ms=int(cegis_ms * 1000),
            total_ms=total_ms,
            depth_max=depth_max,
            cegis_iters=len(counterexamples),
        )
        return SynthesisResult(
            program=program,
            examples=examples,
            counterexamples=counterexamples,
            stats=stats,
            macros_enabled=bool(macros),
            profile=profile,
        )
        # unreachable
    raise RuntimeError("bvps synthesis failed within budget")


def try_fastpath(
    spec: Spec,
    seed: int | None = None,
    *,
    macros: dict[str, MacroTemplate] | None = None,
) -> SynthesisResult | None:
    if not _fastpath_enabled():
        return None
    templates = _fastpath_templates(spec)
    if not templates:
        return None
    total_start = time.perf_counter()
    rng_seed = _resolve_seed(spec, seed)
    interpreter = Interpreter(step_budget=spec.bounds.step_budget)
    examples = _prepare_examples(spec, interpreter)
    oracle_expr = _parse_oracle(spec)
    counterexamples: list[Example] = []
    candidates_tried = 0
    depth_max = 0
    macros = macros or {}
    eval_ms = 0.0
    cegis_ms = 0.0

    for template in templates:
        candidates_tried += 1
        depth_used = bvps_ast.expr_depth(template.body)
        if depth_used > depth_max:
            depth_max = depth_used
        program = expand_program(template, macros)
        eval_start = time.perf_counter()
        passes = _passes_examples(program, examples, interpreter, oracle_expr, spec)
        eval_ms += time.perf_counter() - eval_start
        if not passes:
            continue
        cegis_start = time.perf_counter()
        counterexample = fuzz_counterexample(program, spec, rng_seed, oracle_expr)
        cegis_ms += time.perf_counter() - cegis_start
        if counterexample is not None:
            examples.append(counterexample)
            counterexamples.append(counterexample)
            continue
        stats = SynthesisStats(
            candidates_tried=candidates_tried,
            depth=depth_used,
            counterexamples=len(counterexamples),
            seed=rng_seed,
            fuzz_trials=spec.bounds.fuzz_trials,
        )
        total_ms = int((time.perf_counter() - total_start) * 1000)
        profile = SynthesisProfile(
            enum_ms=0,
            eval_ms=int(eval_ms * 1000),
            cegis_ms=int(cegis_ms * 1000),
            total_ms=total_ms,
            depth_max=depth_max,
            cegis_iters=len(counterexamples),
        )
        return SynthesisResult(
            program=program,
            examples=examples,
            counterexamples=counterexamples,
            stats=stats,
            macros_enabled=bool(macros),
            profile=profile,
            fastpath=True,
        )
    return None


def evaluate_examples(
    program: bvps_ast.Program, spec: Spec, *, step_budget: int | None = None
) -> list[dict[str, Any]]:
    interpreter = Interpreter(step_budget=step_budget or spec.bounds.step_budget)
    oracle_expr = _parse_oracle(spec)
    results: list[dict[str, Any]] = []
    for example in spec.examples:
        expected = example.output
        if expected is None:
            if oracle_expr is None:
                raise ValueError("example missing output and no oracle available")
            expected = _oracle_output(
                example.inputs, oracle_expr, interpreter, spec, program.params
            )
        try:
            output, trace = interpreter.evaluate(program, example.inputs, trace=False)
            results.append(
                {
                    "input": example.inputs,
                    "expected": expected,
                    "output": output,
                    "ok": output == expected,
                    "steps": trace.steps,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "input": example.inputs,
                    "expected": expected,
                    "error": str(exc),
                    "ok": False,
                    "steps": spec.bounds.step_budget,
                }
            )
    return results


def fuzz_counterexample(
    program: bvps_ast.Program,
    spec: Spec,
    seed: int,
    oracle_expr: bvps_ast.Expr | None = None,
) -> Example | None:
    if spec.bounds.fuzz_trials <= 0:
        return None
    oracle_expr = oracle_expr or _parse_oracle(spec)
    if oracle_expr is None:
        return None
    rng = random.Random(seed)
    interpreter = Interpreter(step_budget=spec.bounds.step_budget)
    for _ in range(spec.bounds.fuzz_trials):
        inputs = _random_inputs(spec, rng)
        expected = _oracle_output(inputs, oracle_expr, interpreter, spec, program.params)
        try:
            output, _trace = interpreter.evaluate(program, inputs, trace=False)
        except Exception:
            return Example(inputs=inputs, output=expected)
        if output != expected:
            return Example(inputs=inputs, output=expected)
    return None


def _prepare_examples(spec: Spec, interpreter: Interpreter) -> list[Example]:
    oracle_expr = _parse_oracle(spec)
    examples: list[Example] = []
    for example in spec.examples:
        output = example.output
        if output is None and oracle_expr is not None:
            output = _oracle_output(example.inputs, oracle_expr, interpreter, spec, None)
        examples.append(Example(inputs=example.inputs, output=output))
    return examples


def _passes_examples(
    program: bvps_ast.Program,
    examples: list[Example],
    interpreter: Interpreter,
    oracle_expr: bvps_ast.Expr | None,
    spec: Spec,
) -> bool:
    for example in examples:
        expected = example.output
        if expected is None:
            if oracle_expr is None:
                return False
            expected = _oracle_output(
                example.inputs, oracle_expr, interpreter, spec, program.params
            )
        try:
            output, _trace = interpreter.evaluate(program, example.inputs, trace=False)
        except Exception:
            return False
        if output != expected:
            return False
    return True


def _oracle_output(
    inputs: dict[str, Value],
    oracle_expr: bvps_ast.Expr,
    interpreter: Interpreter,
    spec: Spec,
    params: list[tuple[str, TypeName]] | None,
) -> Value:
    program_params = params or [(item.name, item.type) for item in spec.inputs]
    oracle_program = bvps_ast.Program(
        params=program_params,
        body=oracle_expr,
        return_type=spec.output,
    )
    output, _trace = interpreter.evaluate(oracle_program, inputs, trace=False)
    return output


def _parse_oracle(spec: Spec) -> bvps_ast.Expr | None:
    if spec.oracle is None:
        return None
    return bvps_ast.expr_from_dict(spec.oracle)


def _fastpath_enabled() -> bool:
    value = os.getenv("EIDOLON_BVPS_FASTPATH", "").strip()
    return value in {"1", "true", "True"}


def _fastpath_templates(spec: Spec) -> list[bvps_ast.Program]:
    name = spec.name.strip().lower()
    params = [(item.name, item.type) for item in spec.inputs]
    if name == "abs" and spec.output == "Int" and len(params) == 1 and params[0][1] == "Int":
        var = bvps_ast.Var(params[0][0])
        zero = bvps_ast.IntConst(0)
        body = bvps_ast.IfThenElse(
            cond=bvps_ast.BinOp("lt", var, zero),
            then_expr=bvps_ast.BinOp("sub", zero, var),
            else_expr=var,
        )
        return [bvps_ast.Program(params=params, body=body, return_type="Int")]
    if (
        name == "even"
        and spec.output == "Bool"
        and len(params) == 1
        and params[0][1] == "Int"
    ):
        var = bvps_ast.Var(params[0][0])
        body = bvps_ast.BinOp(
            "eq",
            bvps_ast.BinOp("mod", var, bvps_ast.IntConst(2)),
            bvps_ast.IntConst(0),
        )
        return [bvps_ast.Program(params=params, body=body, return_type="Bool")]
    if (
        name in {"max", "max2"}
        and spec.output == "Int"
        and len(params) == 2
        and params[0][1] == "Int"
        and params[1][1] == "Int"
    ):
        left = bvps_ast.Var(params[0][0])
        right = bvps_ast.Var(params[1][0])
        body = bvps_ast.IfThenElse(
            cond=bvps_ast.BinOp("gt", left, right),
            then_expr=left,
            else_expr=right,
        )
        return [bvps_ast.Program(params=params, body=body, return_type="Int")]
    return []


def _resolve_seed(spec: Spec, seed: int | None) -> int:
    if spec.bounds.seed is not None:
        return int(spec.bounds.seed)
    if seed is not None:
        return int(seed)
    return 0


def _random_inputs(spec: Spec, rng: random.Random) -> dict[str, Value]:
    inputs: dict[str, Value] = {}
    for item in spec.inputs:
        if item.type == "Int":
            inputs[item.name] = rng.randint(spec.bounds.int_min, spec.bounds.int_max)
        else:
            inputs[item.name] = rng.choice([True, False])
    return inputs


def spec_from_payload(payload: dict[str, Any]) -> Spec:
    return spec_from_dict(payload)
