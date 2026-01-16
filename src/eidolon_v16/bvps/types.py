from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TypeName = Literal["Int", "Bool"]
Value = int | bool


@dataclass(frozen=True)
class InputSpec:
    name: str
    type: TypeName


@dataclass(frozen=True)
class Example:
    inputs: dict[str, Value]
    output: Value | None


@dataclass(frozen=True)
class Bounds:
    int_min: int = -5
    int_max: int = 5
    fuzz_trials: int = 20
    max_depth: int = 3
    max_programs: int = 1000
    step_budget: int = 200
    seed: int | None = None


@dataclass(frozen=True)
class Spec:
    name: str
    inputs: list[InputSpec]
    output: TypeName
    examples: list[Example]
    bounds: Bounds
    oracle: dict[str, Any] | None = None


def spec_from_dict(payload: dict[str, Any]) -> Spec:
    name = str(payload.get("name", "bvps"))
    inputs_raw = payload.get("inputs", [])
    inputs = [_input_from_raw(item) for item in inputs_raw]
    output = _parse_type(payload.get("output", "Int"))
    examples = [_example_from_raw(item) for item in payload.get("examples", [])]
    bounds = _bounds_from_raw(payload.get("bounds", {}))
    oracle = payload.get("oracle")
    if oracle is not None and not isinstance(oracle, dict):
        raise TypeError("oracle must be a dict")
    return Spec(
        name=name,
        inputs=inputs,
        output=output,
        examples=examples,
        bounds=bounds,
        oracle=oracle,
    )


def spec_to_dict(spec: Spec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "inputs": [{"name": item.name, "type": item.type} for item in spec.inputs],
        "output": spec.output,
        "examples": [
            {"in": ex.inputs, "out": ex.output}
            for ex in spec.examples
        ],
        "bounds": {
            "int_range": {"min": spec.bounds.int_min, "max": spec.bounds.int_max},
            "fuzz_trials": spec.bounds.fuzz_trials,
            "max_depth": spec.bounds.max_depth,
            "max_programs": spec.bounds.max_programs,
            "step_budget": spec.bounds.step_budget,
            "seed": spec.bounds.seed,
        },
        "oracle": spec.oracle,
    }


def _input_from_raw(raw: Any) -> InputSpec:
    if isinstance(raw, dict):
        name = str(raw.get("name"))
        type_name = _parse_type(raw.get("type"))
        return InputSpec(name=name, type=type_name)
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        name = str(raw[0])
        type_name = _parse_type(raw[1])
        return InputSpec(name=name, type=type_name)
    raise TypeError("input spec must be dict or [name, type]")


def _example_from_raw(raw: Any) -> Example:
    if not isinstance(raw, dict):
        raise TypeError("example must be dict")
    inputs = raw.get("in", {})
    if not isinstance(inputs, dict):
        raise TypeError("example.in must be dict")
    output = raw.get("out")
    return Example(inputs=_normalize_inputs(inputs), output=output)


def _normalize_inputs(inputs: dict[str, Any]) -> dict[str, Value]:
    result: dict[str, Value] = {}
    for key, value in inputs.items():
        if isinstance(value, (bool, int)):
            result[str(key)] = value
        else:
            raise TypeError("example inputs must be int or bool")
    return result


def _bounds_from_raw(raw: Any) -> Bounds:
    if not isinstance(raw, dict):
        return Bounds()
    int_range = raw.get("int_range", {})
    if not isinstance(int_range, dict):
        int_range = {}
    return Bounds(
        int_min=int(int_range.get("min", -5)),
        int_max=int(int_range.get("max", 5)),
        fuzz_trials=int(raw.get("fuzz_trials", 20)),
        max_depth=int(raw.get("max_depth", 3)),
        max_programs=int(raw.get("max_programs", 1000)),
        step_budget=int(raw.get("step_budget", 200)),
        seed=raw.get("seed"),
    )


def _parse_type(value: Any) -> TypeName:
    raw = str(value or "").strip()
    if raw in {"Int", "int"}:
        return "Int"
    if raw in {"Bool", "bool"}:
        return "Bool"
    raise ValueError(f"unknown type {value}")
