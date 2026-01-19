from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any

from eidolon_v16.artifacts.store import ArtifactRef, ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import types as bvps_types
from eidolon_v16.bvps.interp import Interpreter as BvpsInterpreter
from eidolon_v16.eval.generator_families import get_generator_families
from eidolon_v16.skills.bundle import SkillBundle, bundle_identity


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    rationale: str
    evidence_ref: ArtifactRef | None = None


def admit_skill(
    *,
    bundle: SkillBundle,
    store: ArtifactStore,
    seed: int,
) -> AdmissionResult:
    regression = run_regression_gate(bundle, seed=seed)
    sealed = run_sealed_lite_gate(bundle, seed=seed)
    sealed_ref = store.put_json(
        sealed,
        artifact_type=f"skill_sealed_lite:{bundle.spec.name}",
        producer="skills",
        created_from=[ref.hash for ref in bundle.artifact_refs],
    )
    bundle.artifact_refs.append(sealed_ref)
    canary = run_canary_gate(
        bundle,
        sealed_lite=sealed.get("sealed_cases", []),
        tokens=sealed.get("canary_tokens", []),
    )
    admitted = (
        regression["status"] == "PASS"
        and sealed["status"] == "PASS"
        and canary["status"] == "PASS"
    )
    rationale = "PASS" if admitted else "FAIL"
    identity = bundle_identity(bundle)
    evidence_payload = {
        "skill": {"name": bundle.spec.name, "version": bundle.spec.version},
        "bundle": identity,
        "regression": regression,
        "sealed_lite": sealed,
        "sealed_lite_artifact": sealed_ref.hash,
        "canary": canary,
        "admitted": admitted,
    }
    evidence_ref = store.put_json(
        evidence_payload,
        artifact_type=f"skill_admission:{bundle.spec.name}",
        producer="skills",
        created_from=[ref.hash for ref in bundle.artifact_refs],
    )
    return AdmissionResult(admitted=admitted, rationale=rationale, evidence_ref=evidence_ref)


def run_regression_gate(bundle: SkillBundle, seed: int) -> dict[str, Any]:
    program = bvps_ast.program_from_dict(bundle.program)
    tests = bundle.tests
    cases = tests.get("cases", [])
    oracle = tests.get("oracle")
    fuzz_trials = int(tests.get("fuzz_trials", 5))
    fuzz_seed = int(tests.get("fuzz_seed", seed))
    interpreter = BvpsInterpreter(step_budget=_step_budget(bundle))
    oracle_expr = _load_oracle(oracle)
    failures: list[dict[str, Any]] = []
    for case in cases:
        inputs = case.get("in", {})
        expected = case.get("out")
        if _eval_case(program, inputs, expected, interpreter):
            continue
        failures.append({"input": inputs, "expected": expected})
        break
    if not failures and oracle_expr is not None:
        for sample in _fuzz_inputs(bundle, fuzz_seed, fuzz_trials):
            expected = _oracle_output(sample, oracle_expr, interpreter, bundle)
            if _eval_case(program, sample, expected, interpreter):
                continue
            failures.append({"input": sample, "expected": expected})
            break
    status = "PASS" if not failures else "FAIL"
    return {"status": status, "failures": failures}


def run_sealed_lite_gate(bundle: SkillBundle, seed: int) -> dict[str, Any]:
    program = bvps_ast.program_from_dict(bundle.program)
    interpreter = BvpsInterpreter(step_budget=_step_budget(bundle))
    families = get_generator_families()
    base_spec = bundle.spec.model_dump(mode="json")
    family_results: list[dict[str, Any]] = []
    sealed_cases: list[dict[str, Any]] = []
    overall_status = "PASS"
    for idx, family in enumerate(families):
        family_seed = seed + idx * 101
        specs = family.generate(base_spec, family_seed)
        variant_results: list[dict[str, Any]] = []
        for spec in specs:
            variant_results.append(_evaluate_spec(program, spec, interpreter))
            mutated = family.mutate(spec, family_seed + 7)
            variant_results.append(_evaluate_spec(program, mutated, interpreter))
        family_pass = all(item["pass"] for item in variant_results)
        family_status = "PASS" if family_pass else "FAIL"
        overall_status = "FAIL" if family_status == "FAIL" else overall_status
        sealed_cases.extend(
            [
                {
                    "family": family.name,
                    "spec": item["spec"],
                    "cases": item["cases"],
                }
                for item in variant_results
            ]
        )
        family_results.append(
            {
                "family": family.name,
                "status": family_status,
                "variants": variant_results,
            }
        )
    return {
        "status": overall_status,
        "families": family_results,
        "sealed_cases": sealed_cases,
        "canary_tokens": [family.canary_token for family in families],
    }


def run_canary_gate(
    bundle: SkillBundle,
    sealed_lite: list[dict[str, Any]],
    tokens: list[str],
) -> dict[str, Any]:
    if not tokens:
        return {"status": "PASS", "hits": [], "tokens": tokens}
    bundle_text = json.dumps(
        {
            "spec": bundle.spec.model_dump(mode="json"),
            "program": bundle.program,
            "tests": bundle.tests,
            "verify_profile": bundle.verify_profile,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    hits = [token for token in tokens if token and token in bundle_text]
    status = "PASS" if not hits else "FAIL"
    return {"status": status, "hits": hits, "tokens": tokens}


def _step_budget(bundle: SkillBundle) -> int:
    bounds = bundle.spec.preconditions.get("bounds", {})
    return int(bounds.get("step_budget", 200))


def _load_oracle(oracle: Any) -> bvps_ast.Expr | None:
    if oracle is None:
        return None
    if isinstance(oracle, dict):
        return bvps_ast.expr_from_dict(oracle)
    return None


def _eval_case(
    program: bvps_ast.Program,
    inputs: dict[str, Any],
    expected: Any,
    interpreter: BvpsInterpreter,
) -> bool:
    try:
        output, _trace = interpreter.evaluate(program, inputs, trace=False)
    except Exception:
        return False
    if isinstance(expected, bool):
        expected_value: bvps_types.Value = expected
    elif isinstance(expected, int):
        expected_value = expected
    else:
        return False
    return output == expected_value


def _evaluate_spec(
    program: bvps_ast.Program,
    spec: dict[str, Any],
    interpreter: BvpsInterpreter,
) -> dict[str, Any]:
    spec_name = str(spec.get("name", "spec"))
    cases = []
    success = True
    oracle_expr = _load_oracle(spec.get("oracle"))
    for example in spec.get("examples", []):
        inputs = example.get("in", {})
        expected = example.get("out")
        if expected is None and oracle_expr is not None:
            expected = _oracle_output_for_spec(spec, inputs, interpreter, oracle_expr)
        passed = _eval_case(program, inputs, expected, interpreter)
        cases.append({"input": inputs, "expected": expected, "pass": passed})
        success = success and passed
    return {"spec": spec_name, "pass": success, "cases": cases}


def _oracle_output_for_spec(
    spec: dict[str, Any],
    inputs: dict[str, Any],
    interpreter: BvpsInterpreter,
    oracle_expr: bvps_ast.Expr,
) -> bvps_types.Value:
    spec_model = bvps_types.spec_from_dict(
        {
            "name": spec.get("name", "spec"),
            "inputs": spec.get("inputs", []),
            "output": spec.get("output", "Int"),
            "examples": spec.get("examples", []),
            "bounds": spec.get("bounds", {}),
            "oracle": spec.get("oracle"),
        }
    )
    oracle_program = bvps_ast.Program(
        params=[(item.name, item.type) for item in spec_model.inputs],
        body=oracle_expr,
        return_type=spec_model.output,
    )
    output, _trace = interpreter.evaluate(oracle_program, inputs, trace=False)
    return output


def _oracle_output(
    inputs: dict[str, Any],
    oracle_expr: bvps_ast.Expr,
    interpreter: BvpsInterpreter,
    bundle: SkillBundle,
) -> bvps_types.Value:
    spec = _bundle_spec(bundle)
    oracle_program = bvps_ast.Program(
        params=[(item.name, item.type) for item in spec.inputs],
        body=oracle_expr,
        return_type=spec.output,
    )
    output, _trace = interpreter.evaluate(oracle_program, inputs, trace=False)
    return output


def _bundle_spec(bundle: SkillBundle) -> bvps_types.Spec:
    io_schema = bundle.spec.io_schema
    spec_payload = {
        "name": bundle.spec.name,
        "inputs": io_schema.get("inputs", []),
        "output": io_schema.get("output", "Int"),
        "examples": [],
        "bounds": bundle.spec.preconditions.get("bounds", {}),
        "oracle": bundle.tests.get("oracle"),
    }
    return bvps_types.spec_from_dict(spec_payload)


def _fuzz_inputs(bundle: SkillBundle, seed: int, trials: int) -> list[dict[str, Any]]:
    spec = _bundle_spec(bundle)
    rng = random.Random(seed)
    samples: list[dict[str, Any]] = []
    for _ in range(trials):
        inputs: dict[str, Any] = {}
        for item in spec.inputs:
            if item.type == "Int":
                inputs[item.name] = rng.randint(spec.bounds.int_min, spec.bounds.int_max)
            else:
                inputs[item.name] = rng.choice([True, False])
        samples.append(inputs)
    return samples
