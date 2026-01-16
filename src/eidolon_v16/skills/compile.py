from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import types as bvps_types
from eidolon_v16.bvps.interp import Interpreter as BvpsInterpreter
from eidolon_v16.skills.bundle import SkillBundle, write_skill_bundle
from eidolon_v16.skills.spec import SkillImpl, SkillSpec, TriggerSpec
from eidolon_v16.ucr.models import LaneVerdict, TaskInput


def compile_skill_from_bvps(
    *,
    task: TaskInput,
    solution: dict[str, Any],
    lanes: list[LaneVerdict],
    store: ArtifactStore,
    episode_id: str,
    seed: int,
) -> SkillBundle | None:
    if task.normalized.get("kind") != "bvps":
        return None
    if not _lanes_pass(lanes, {"translation", "consequence"}):
        return None
    spec_payload = task.normalized.get("data", {}).get("bvps_spec")
    program_payload = solution.get("program")
    if not isinstance(spec_payload, dict) or not isinstance(program_payload, dict):
        return None
    spec = bvps_types.spec_from_dict(spec_payload)
    program = bvps_ast.program_from_dict(program_payload)
    generalized_program = _generalize_constants(program, spec)
    program_ast = generalized_program.to_dict()

    oracle = spec.oracle
    tests_payload = _build_tests_payload(spec, generalized_program, oracle, seed)
    trace = solution.get("trace", {})
    report_hash = trace.get("bvps_report") if isinstance(trace, dict) else None
    if isinstance(report_hash, str):
        try:
            report_payload = store.read_json_by_hash(report_hash)
        except Exception:
            report_payload = {}
        counterexamples = report_payload.get("counterexamples", [])
        tests_payload["counterexamples"] = counterexamples
        tests_payload["cases"].extend(
            [{"in": item.get("in", {}), "out": item.get("out")} for item in counterexamples]
        )
        tests_payload["cases"] = _dedupe_cases(tests_payload["cases"])
    verify_profile = {"lanes": ["recompute", "translation", "consequence"], "require_all": True}

    created_ts = _utc_now()
    skill_spec = SkillSpec(
        name=str(spec.name),
        version="v0",
        created_ts_utc=created_ts,
        origin_episode_id=episode_id,
        triggers=_bvps_triggers(spec),
        io_schema={
            "inputs": [{"name": item.name, "type": item.type} for item in spec.inputs],
            "output": spec.output,
        },
        preconditions={"bounds": spec_payload.get("bounds", {})},
        verifier_profile=verify_profile,
        cost_profile={"cpu_ms": 0, "steps": spec.bounds.step_budget},
        impl=SkillImpl(
            kind="bvps_ast",
            program=program_ast,
            dsl_version="bvps/v1",
        ),
        artifacts=[],
    )
    return write_skill_bundle(
        store=store,
        skill_spec=skill_spec,
        program_ast=program_ast,
        tests=tests_payload,
        verify_profile=verify_profile,
    )


def _lanes_pass(lanes: list[LaneVerdict], required: set[str]) -> bool:
    statuses = {lane.lane: lane.status for lane in lanes}
    return all(statuses.get(lane) == "PASS" for lane in required)


def _generalize_constants(
    program: bvps_ast.Program, spec: bvps_types.Spec
) -> bvps_ast.Program:
    _ = spec
    return program


def _build_tests_payload(
    spec: bvps_types.Spec,
    program: bvps_ast.Program,
    oracle: dict[str, Any] | None,
    seed: int,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for example in spec.examples:
        if example.output is None:
            continue
        cases.append({"in": example.inputs, "out": example.output})
    if oracle is not None:
        interpreter = BvpsInterpreter(step_budget=spec.bounds.step_budget)
        oracle_expr = bvps_ast.expr_from_dict(oracle)
        for sample in _fuzz_inputs(spec, seed, trials=max(1, spec.bounds.fuzz_trials)):
            expected = _oracle_output(sample, oracle_expr, interpreter, spec, program.params)
            cases.append({"in": sample, "out": expected})
    return {
        "fuzz_seed": seed,
        "fuzz_trials": max(1, spec.bounds.fuzz_trials),
        "cases": _dedupe_cases(cases),
        "oracle": oracle,
    }


def _oracle_output(
    inputs: dict[str, bvps_types.Value],
    oracle_expr: bvps_ast.Expr,
    interpreter: BvpsInterpreter,
    spec: bvps_types.Spec,
    params: list[tuple[str, bvps_types.TypeName]],
) -> bvps_types.Value:
    oracle_program = bvps_ast.Program(
        params=params,
        body=oracle_expr,
        return_type=spec.output,
    )
    output, _trace = interpreter.evaluate(oracle_program, inputs, trace=False)
    return output


def _fuzz_inputs(
    spec: bvps_types.Spec, seed: int, trials: int
) -> list[dict[str, bvps_types.Value]]:
    rng = random.Random(seed)
    samples: list[dict[str, bvps_types.Value]] = []
    for _ in range(trials):
        inputs: dict[str, bvps_types.Value] = {}
        for item in spec.inputs:
            if item.type == "Int":
                inputs[item.name] = rng.randint(spec.bounds.int_min, spec.bounds.int_max)
            else:
                inputs[item.name] = rng.choice([True, False])
        samples.append(inputs)
    return samples


def _dedupe_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for case in cases:
        key = f"{case.get('in')}-{case.get('out')}"
        if key in seen:
            continue
        seen.add(key)
        ordered.append(case)
    return ordered


def _bvps_triggers(spec: bvps_types.Spec) -> TriggerSpec:
    name = str(spec.name or "").strip()
    keywords = [name] if name else []
    return TriggerSpec(task_contains=keywords, task_family="bvps")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
