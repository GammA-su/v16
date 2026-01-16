from __future__ import annotations

import random
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


def synthesize(
    spec: Spec,
    seed: int | None = None,
    *,
    macros: dict[str, MacroTemplate] | None = None,
) -> SynthesisResult:
    rng_seed = _resolve_seed(spec, seed)
    interpreter = Interpreter(step_budget=spec.bounds.step_budget)
    examples = _prepare_examples(spec, interpreter)
    oracle_expr = _parse_oracle(spec)
    counterexamples: list[Example] = []
    candidates_tried = 0
    depth_used = 0
    macros = macros or {}

    for candidate in bvps_enumerate.enumerate_programs(spec, macros=macros):
        candidates_tried += 1
        depth_used = bvps_ast.expr_depth(candidate.body)
        program = expand_program(candidate, macros)
        if not _passes_examples(program, examples, interpreter, oracle_expr, spec):
            if candidates_tried >= spec.bounds.max_programs:
                break
            continue
        counterexample = fuzz_counterexample(program, spec, rng_seed, oracle_expr)
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
        return SynthesisResult(
            program=program,
            examples=examples,
            counterexamples=counterexamples,
            stats=stats,
            macros_enabled=bool(macros),
        )
        # unreachable
    raise RuntimeError("bvps synthesis failed within budget")


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
