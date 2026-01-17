from __future__ import annotations

import itertools
import re
from typing import Any

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps.interp import Interpreter
from eidolon_v16.bvps.types import TypeName

Signature = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)?\s*\((?P<inputs>[^)]*)\)\s*->\s*(?P<output>[A-Za-z_][A-Za-z0-9_]*)\s*$"
)


def parse_bvps_prompt(prompt: str) -> dict[str, Any] | None:
    text = prompt.strip()
    if text.upper().startswith("BVPS:"):
        payload = text[len("BVPS:") :].strip()
    elif text.upper().startswith("SYNTH:"):
        payload = text[len("SYNTH:") :].strip()
    else:
        return None
    match = Signature.match(payload)
    if not match:
        return None
    name = match.group("name") or "bvps"
    inputs_raw = match.group("inputs").strip()
    output_type = _normalize_type(match.group("output"))
    input_types = [
        _normalize_type(token.strip()) for token in inputs_raw.split(",") if token.strip()
    ]
    param_names = [f"x{i}" for i in range(len(input_types))]

    oracle_expr = _oracle_expression(name.lower(), param_names, input_types, output_type)
    examples = []
    if oracle_expr is not None:
        examples = _build_examples(param_names, input_types, output_type, oracle_expr)

    spec = {
        "name": name,
        "inputs": [
        {"name": param, "type": type_name}
        for param, type_name in zip(param_names, input_types, strict=True)
        ],
        "output": output_type,
        "examples": examples,
        "bounds": {"max_depth": 3, "max_programs": 500, "fuzz_trials": 10},
    }
    if oracle_expr is not None:
        spec["oracle"] = oracle_expr.to_dict()
    return spec


def _normalize_type(value: str | None) -> TypeName:
    if value is None:
        return "Int"
    text = value.strip().lower()
    if text in {"int", "integer"}:
        return "Int"
    if text in {"bool", "boolean"}:
        return "Bool"
    return "Int"


def _oracle_expression(
    name: str, params: list[str], param_types: list[TypeName], output_type: TypeName
) -> bvps_ast.Expr | None:
    if name == "abs" and len(params) == 1 and output_type == "Int":
        var = bvps_ast.Var(params[0])
        zero = bvps_ast.IntConst(0)
        return bvps_ast.IfThenElse(
            cond=bvps_ast.BinOp("lt", var, zero),
            then_expr=bvps_ast.BinOp("sub", zero, var),
            else_expr=var,
        )
    return None


def _build_examples(
    params: list[str],
    types: list[TypeName],
    ret_type: TypeName,
    oracle_expr: bvps_ast.Expr,
) -> list[dict[str, Any]]:
    interpreter = Interpreter(step_budget=100)
    program = bvps_ast.Program(
        params=list(zip(params, types, strict=True)),
        body=oracle_expr,
        return_type=ret_type,
    )
    samples = _input_samples(types, limit=4)
    examples: list[dict[str, Any]] = []
    for sample in samples:
        output, _trace = interpreter.evaluate(program, sample, trace=False)
        examples.append({"in": sample, "out": output})
    return examples


def _input_samples(types: list[TypeName], limit: int = 4) -> list[dict[str, Any]]:
    values_map: dict[str, list[Any]] = {"Int": [-2, -1, 0, 1, 2], "Bool": [False, True]}
    sequences: list[list[Any]] = []
    for typ in types:
        sequences.append(values_map.get(typ, [0]))
    combos = list(itertools.product(*sequences))
    samples: list[dict[str, Any]] = []
    for combo in combos[:limit]:
        sample: dict[str, Any] = {}
        for idx, value in enumerate(combo):
            sample[f"x{idx}"] = value
        samples.append(sample)
    return samples
