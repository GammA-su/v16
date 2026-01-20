from __future__ import annotations

import itertools
import logging
import math
import random
import time
from typing import Any, Literal

from eidolon_v16.arith_types import canonicalize_number
from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import cegis as bvps_cegis
from eidolon_v16.bvps import types as bvps_types
from eidolon_v16.bvps.dsl import program_from_dict
from eidolon_v16.bvps.interp import Interpreter as BvpsInterpreter
from eidolon_v16.bvps.interpreter import Interpreter
from eidolon_v16.bvps.synth import spec_function
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.ucr.canonical import sha256_bytes, sha256_canonical
from eidolon_v16.ucr.models import Interpretation, LaneVerdict, TaskInput
from eidolon_v16.utils import safe_eval_arith
from eidolon_v16.worldlab.gridworld import GridWorld
from eidolon_v16.worldlab.runner import run_rollout

logger = logging.getLogger(__name__)

Status = Literal["PASS", "FAIL", "BORDERLINE"]
BVPS_INT_OPS = {"add", "sub", "mul", "mod"}
BVPS_BOOL_OPS = {"lt", "gt", "eq"}
BVPS_ALLOWED_OPS = BVPS_INT_OPS | BVPS_BOOL_OPS


def _duration_ms(start: float) -> float:
    duration_ms = (time.perf_counter() - start) * 1000.0
    if duration_ms < 0:
        return 0.0
    return duration_ms


def _cost_ms(duration_ms: float) -> int:
    if duration_ms <= 0:
        return 0
    return max(1, int(math.ceil(duration_ms)))


def run_lanes(
    task: TaskInput,
    chosen: Interpretation,
    solution: dict[str, Any],
    store: ArtifactStore,
    *,
    seed: int,
) -> tuple[list[LaneVerdict], dict[str, int], int]:
    def _timed_run(
        func: Any, *args: Any, **kwargs: Any
    ) -> tuple[LaneVerdict, int, int]:
        start = time.perf_counter()
        verdict, duration_ms = func(*args, **kwargs)
        lane_exec_ms = _cost_ms(duration_ms)
        elapsed_ms = int(round((time.perf_counter() - start) * 1000))
        if elapsed_ms < 0:
            elapsed_ms = 0
        artifact_ms = max(0, elapsed_ms - lane_exec_ms)
        verdict.cost_ms = lane_exec_ms
        verdict.costs = dict(verdict.costs or {})
        verdict.costs["ms"] = lane_exec_ms
        verdict.costs["artifact_ms"] = artifact_ms
        return verdict, lane_exec_ms, artifact_ms

    recompute, recompute_ms, recompute_artifact_ms = _timed_run(
        run_recompute, task, solution, store
    )
    translation, translation_ms, translation_artifact_ms = _timed_run(
        run_translation, task, chosen, solution, store, seed
    )
    consequence, consequence_ms, consequence_artifact_ms = _timed_run(
        run_consequence, task, solution, store, seed
    )
    anchors, anchors_ms, anchors_artifact_ms = _timed_run(
        run_anchors, [recompute, translation, consequence], store
    )
    lanes = [recompute, translation, consequence, anchors]
    lane_ms = {
        "recompute": recompute_ms,
        "translation": translation_ms,
        "consequence": consequence_ms,
        "anchors": anchors_ms,
    }
    artifact_ms = (
        recompute_artifact_ms
        + translation_artifact_ms
        + consequence_artifact_ms
        + anchors_artifact_ms
    )
    return lanes, lane_ms, artifact_ms



def task_signature(task: TaskInput) -> dict[str, Any]:
    normalized = task.normalized
    kind = str(normalized.get("kind", "unknown"))
    data = normalized.get("data", {})
    signature: dict[str, Any] = {"kind": kind}
    if kind == "arith":
        signature["expression"] = str(data.get("expression", ""))
    elif kind == "list":
        signature["operation"] = str(data.get("operation", ""))
    elif kind == "world":
        signature["goal"] = data.get("goal")
        signature["width"] = data.get("width")
        signature["height"] = data.get("height")
    return signature


def _world_from_task(task: TaskInput) -> GridWorld:
    data = task.normalized.get("data", {}) or {}
    width = int(data.get("width", 3))
    height = int(data.get("height", 3))
    goal = _coerce_goal(data.get("goal"))
    blocked = _coerce_blocked(data.get("blocked"))
    return GridWorld(width=width, height=height, goal=goal, blocked=blocked)


def _coerce_goal(value: Any) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            pass
    return 2, 2


def _coerce_blocked(value: Any) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    if not isinstance(value, list):
        return blocked
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            try:
                blocked.add((int(item[0]), int(item[1])))
            except (TypeError, ValueError):
                continue
    return blocked


def _required_field_errors(
    kind: str, solution: dict[str, Any], signature: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if kind == "arith":
        solution_expr = solution.get("expression")
        if solution_expr not in (None, "") and str(solution_expr) != signature.get("expression"):
            errors.append("expression mismatch")
        if "output" not in solution:
            errors.append("missing solution.output")
    elif kind == "list":
        if "program" not in solution:
            errors.append("missing solution.program")
        if "input" not in solution:
            errors.append("missing solution.input")
        if "output" not in solution:
            errors.append("missing solution.output")
        if "operation" in solution and solution.get("operation") != signature.get("operation"):
            errors.append("operation mismatch")
    elif kind == "bvps":
        if "program" not in solution:
            errors.append("missing solution.program")
    elif kind == "world":
        if "actions" not in solution:
            errors.append("missing solution.actions")
        if "world" not in solution:
            errors.append("missing solution.world")
        world = solution.get("world") or {}
        if signature.get("goal") is not None and world.get("goal") != signature.get("goal"):
            errors.append("goal mismatch")
        if signature.get("width") is not None and world.get("width") != signature.get("width"):
            errors.append("width mismatch")
        if signature.get("height") is not None and world.get("height") != signature.get("height"):
            errors.append("height mismatch")
    return errors


def run_recompute(
    task: TaskInput, solution: dict[str, Any], store: ArtifactStore
) -> tuple[LaneVerdict, float]:
    start = time.perf_counter()
    logger.info("recompute lane start")
    kind = task.normalized.get("kind", "unknown")
    status: Status = "FAIL"
    details: dict[str, Any] = {"kind": kind}
    if kind == "arith":
        expr = str(task.normalized.get("data", {}).get("expression", "0"))
        expected = solution.get("output")
        try:
            computed = safe_eval_arith(expr)
        except Exception as exc:
            status = "FAIL"
            details.update({"expression": expr, "error": str(exc)})
        else:
            computed_value = canonicalize_number(computed)
            try:
                expected_value = canonicalize_number(expected)
            except TypeError as exc:
                status = "FAIL"
                details.update(
                    {
                        "expression": expr,
                        "computed": computed_value,
                        "expected": expected,
                        "error": str(exc),
                    }
                )
            else:
                status = "PASS" if computed_value == expected_value else "FAIL"
                details.update(
                    {"expression": expr, "computed": computed_value, "expected": expected_value}
                )
    elif kind == "bvps":
        data = task.normalized.get("data", {})
        spec_payload = data.get("bvps_spec")
        program_payload = solution.get("program")
        if not isinstance(spec_payload, dict) or not isinstance(program_payload, dict):
            details["error"] = "missing bvps spec/program"
        else:
            bvps_spec = bvps_types.spec_from_dict(spec_payload)
            bvps_program = bvps_ast.program_from_dict(program_payload)
            checks = bvps_cegis.evaluate_examples(bvps_program, bvps_spec)
            status = "PASS" if all(item["ok"] for item in checks) else "FAIL"
            details.update({"checks": checks})
    elif kind == "list":
        list_program = program_from_dict(solution["program"])
        interpreter = Interpreter(step_limit=2000)
        output, trace = interpreter.run(list_program, [solution["input"]])
        expected = solution.get("output")
        status = "PASS" if output == expected else "FAIL"
        details.update({"computed": output, "expected": expected, "trace": trace})
    elif kind == "world":
        actions = solution.get("actions", [])
        world = _world_from_task(task)
        rollout = run_rollout(world, actions, seed=0)
        status = "PASS" if rollout["done"] else "FAIL"
        details.update({"rollout": rollout})
    else:
        details["error"] = "unsupported kind"
    duration_ms = _duration_ms(start)
    details["duration_ms"] = duration_ms
    evidence = store.put_json(details, artifact_type="lane_recompute", producer="verify")
    logger.info("recompute lane status=%s", status)
    cost_ms = _cost_ms(duration_ms)
    return (
        LaneVerdict(
            lane="recompute",
            status=status,
            cost_ms=cost_ms,
            evidence=[evidence],
            costs={"ms": cost_ms},
        ),
        duration_ms,
    )


def run_translation(
    task: TaskInput,
    chosen: Interpretation,
    solution: dict[str, Any],
    store: ArtifactStore,
    seed: int,
    attempt: int | None = None,
) -> tuple[LaneVerdict, float]:
    logger.info("translation lane start")
    kernel = StubKernel()
    signature = task_signature(task)
    kind = signature.get("kind", "unknown")
    start = time.perf_counter()
    if kind == "arith":
        expr = _arith_expression(task, signature)
        if expr:
            signature["expression"] = expr
    errors = _required_field_errors(str(kind), solution, signature)

    if kind == "arith":
        expr = _arith_expression(task, signature)
        expected = solution.get("output")
        evidence_payload: dict[str, Any]
        arith_status: Status = "FAIL"
        try:
            computed = safe_eval_arith(expr)
        except Exception as exc:
            arith_status = "FAIL"
            evidence_payload = {
                "signature": signature,
                "required_field_errors": errors,
                "expression": expr,
                "expected": expected,
                "error": str(exc),
            }
        else:
            computed_value = canonicalize_number(computed)
            try:
                expected_value = canonicalize_number(expected)
            except TypeError as exc:
                arith_status = "FAIL"
                evidence_payload = {
                    "signature": signature,
                    "required_field_errors": errors,
                    "expression": expr,
                    "computed": computed_value,
                    "expected": expected,
                    "error": str(exc),
                }
            else:
                arith_status = "PASS" if computed_value == expected_value and not errors else "FAIL"
                evidence_payload = {
                    "signature": signature,
                    "required_field_errors": errors,
                    "expression": expr,
                    "computed": computed_value,
                    "expected": expected_value,
                }
        duration_ms = _duration_ms(start)
        evidence_payload["duration_ms"] = duration_ms
        artifact_type = "translation_arith"
        evidence = store.put_json(
            evidence_payload,
            artifact_type=artifact_type,
            producer="verify",
        )
        logger.info("translation lane status=%s", arith_status)
        cost_ms = _cost_ms(duration_ms)
        verdict = LaneVerdict(
            lane="translation",
            status=arith_status,
            cost_ms=cost_ms,
            evidence=[evidence],
            costs={"ms": cost_ms},
        )
        return verdict, duration_ms

    if kind == "bvps":
        data = task.normalized.get("data", {})
        spec_payload = data.get("bvps_spec")
        program_payload = solution.get("program")
        bvps_status: Status = "FAIL"
        bvps_evidence_payload: dict[str, Any]
        if not isinstance(spec_payload, dict) or not isinstance(program_payload, dict):
            bvps_evidence_payload = {
                "signature": signature,
                "required_field_errors": errors,
                "error": "missing bvps spec/program",
            }
        else:
            bvps_spec = bvps_types.spec_from_dict(spec_payload)
            bvps_program = bvps_ast.program_from_dict(program_payload)
            type_errors = _bvps_signature_errors(bvps_spec, bvps_program)
            type_check_errors = _bvps_type_errors(bvps_program)
            op_errors = _bvps_op_errors(bvps_program)
            pretty = bvps_ast.expr_to_str(bvps_program.body)
            ast_hash = sha256_canonical(bvps_program.to_dict())
            pretty_hash = sha256_bytes(pretty.encode("utf-8"))
            mismatch_errors = _bvps_program_mismatch_errors(solution, pretty, ast_hash)
            all_errors = errors + type_errors + type_check_errors + op_errors + mismatch_errors
            bvps_status = "PASS" if not all_errors else "FAIL"
            bvps_evidence_payload = {
                "signature": signature,
                "required_field_errors": errors,
                "type_errors": type_errors,
                "type_check_errors": type_check_errors,
                "op_errors": op_errors,
                "mismatch_errors": mismatch_errors,
                "program_pretty": pretty,
                "program_hash": ast_hash,
                "program_pretty_hash": pretty_hash,
                "attempt": attempt or 1,
            }
        duration_ms = _duration_ms(start)
        bvps_evidence_payload["duration_ms"] = duration_ms
        artifact_type = "translation_bvps" if (attempt or 1) == 1 else "translation_bvps_attempt2"
        evidence = store.put_json(
            bvps_evidence_payload,
            artifact_type=artifact_type,
            producer="verify",
        )
        logger.info("translation lane status=%s", bvps_status)
        cost_ms = _cost_ms(duration_ms)
        verdict = LaneVerdict(
            lane="translation",
            status=bvps_status,
            cost_ms=cost_ms,
            evidence=[evidence],
            costs={"ms": cost_ms},
        )
        return verdict, duration_ms

    alt_seed = seed + 1000
    alt_interpretations = kernel.propose_interpretations(task, seed=alt_seed)
    alt_interpretations.sort(key=lambda item: item.interpretation_id)
    alt_interpretation = alt_interpretations[0] if alt_interpretations else chosen
    alt_solution = kernel.propose_solution(task, alt_interpretation, seed=alt_seed)

    mismatch = solution.get("output") != alt_solution.output
    if errors:
        status: Status = "FAIL"
    elif mismatch:
        status = (
            "BORDERLINE"
            if alt_interpretation.interpretation_id != chosen.interpretation_id
            else "FAIL"
        )
    else:
        status = "PASS"

    evidence_payload = {
        "signature": signature,
        "chosen": chosen.model_dump(mode="json"),
        "alt_interpretation": alt_interpretation.model_dump(mode="json"),
        "solution_output": solution.get("output"),
        "alt_output": alt_solution.output,
        "required_field_errors": errors,
        "mismatch": mismatch,
    }
    duration_ms = _duration_ms(start)
    evidence_payload["duration_ms"] = duration_ms
    evidence = store.put_json(
        evidence_payload,
        artifact_type="lane_translation",
        producer="verify",
    )
    logger.info("translation lane status=%s", status)
    cost_ms = _cost_ms(duration_ms)
    verdict = LaneVerdict(
        lane="translation",
        status=status,
        cost_ms=cost_ms,
        evidence=[evidence],
        costs={"ms": cost_ms},
    )
    return verdict, duration_ms


def run_consequence(
    task: TaskInput,
    solution: dict[str, Any],
    store: ArtifactStore,
    seed: int,
    attempt: int | None = None,
) -> tuple[LaneVerdict, float]:
    logger.info("consequence lane start")
    kind = task.normalized.get("kind", "unknown")
    status: Status = "FAIL"
    details: dict[str, Any] = {"kind": kind}
    start = time.perf_counter()
    rng = random.Random(seed)
    if kind == "arith":
        expr = str(task.normalized.get("data", {}).get("expression", "0"))
        expected = solution.get("output")
        try:
            computed = safe_eval_arith(expr)
        except Exception as exc:
            status = "FAIL"
            details.update({"expression": expr, "error": str(exc)})
        else:
            computed_value = canonicalize_number(computed)
            try:
                expected_value = canonicalize_number(expected)
            except TypeError as exc:
                status = "FAIL"
                details.update(
                    {
                        "expression": expr,
                        "computed": computed_value,
                        "expected": expected,
                        "error": str(exc),
                    }
                )
            else:
                status = "PASS" if computed_value == expected_value else "FAIL"
                details.update(
                    {"expression": expr, "computed": computed_value, "expected": expected_value}
                )
    elif kind == "bvps":
        data = task.normalized.get("data", {})
        spec_payload = data.get("bvps_spec")
        program_payload = solution.get("program")
        if not isinstance(spec_payload, dict) or not isinstance(program_payload, dict):
            details["error"] = "missing bvps spec/program"
        else:
            bvps_spec = bvps_types.spec_from_dict(spec_payload)
            bvps_program = bvps_ast.program_from_dict(program_payload)
            status, details = _bvps_consequence_details(
                bvps_spec, bvps_program, seed=seed, attempt=attempt or 1
            )
    elif kind == "list":
        list_program = program_from_dict(solution["program"])
        interpreter = Interpreter(step_limit=2000)
        operation = str(task.normalized.get("data", {}).get("operation", "sum"))
        spec_fn = spec_function(operation)
        list_counterexample = None
        for _ in range(10):
            length = rng.randint(0, 5)
            sample = [rng.randint(-3, 6) for _ in range(length)]
            expected = spec_fn(sample)
            output, _trace = interpreter.run(list_program, [sample])
            if output != expected:
                list_counterexample = {"input": sample, "expected": expected, "output": output}
                break
        status = "PASS" if list_counterexample is None else "FAIL"
        details.update({"operation": operation, "counterexample": list_counterexample})
    elif kind == "world":
        actions = solution.get("actions", [])
        world = _world_from_task(task)
        rollout = run_rollout(world, actions, seed=seed)
        status = "PASS" if rollout["done"] else "FAIL"
        details.update({"rollout": rollout})
    else:
        details["error"] = "unsupported kind"
    if kind == "bvps":
        artifact_type = (
            "consequence_bvps" if (attempt or 1) == 1 else "consequence_bvps_attempt2"
        )
    else:
        artifact_type = "lane_consequence"
    duration_ms = _duration_ms(start)
    details["duration_ms"] = duration_ms
    evidence = store.put_json(details, artifact_type=artifact_type, producer="verify")
    logger.info("consequence lane status=%s", status)
    cost_ms = _cost_ms(duration_ms)
    return (
        LaneVerdict(
            lane="consequence",
            status=status,
            cost_ms=cost_ms,
            evidence=[evidence],
            costs={"ms": cost_ms},
        ),
        duration_ms,
    )


def run_anchors(lanes: list[LaneVerdict], store: ArtifactStore) -> tuple[LaneVerdict, float]:
    logger.info("anchors lane start")
    start = time.perf_counter()
    issues = []
    for lane in lanes:
        if lane.status == "PASS" and not lane.evidence:
            issues.append(f"lane {lane.lane} has PASS without evidence")
    status: Status = "PASS" if not issues else "FAIL"
    evidence = store.put_json(
        {"issues": issues, "lane_status": {lane.lane: lane.status for lane in lanes}},
        artifact_type="lane_anchors",
        producer="verify",
    )
    duration_ms = _duration_ms(start)
    logger.info("anchors lane status=%s", status)
    cost_ms = _cost_ms(duration_ms)
    return (
        LaneVerdict(
            lane="anchors",
            status=status,
            cost_ms=cost_ms,
            evidence=[evidence],
            costs={"ms": cost_ms},
        ),
        duration_ms,
    )


def _bvps_signature_errors(spec: bvps_types.Spec, program: bvps_ast.Program) -> list[str]:
    errors: list[str] = []
    if len(program.params) != len(spec.inputs):
        errors.append("program parameter count mismatch")
    for spec_input, param in itertools.zip_longest(spec.inputs, program.params):
        if spec_input is None or param is None:
            continue
        param_name, param_type = param
        if param_name != spec_input.name:
            errors.append(f"param name mismatch: {param_name} != {spec_input.name}")
        if param_type != spec_input.type:
            errors.append(f"param type mismatch for {param_name}")
    if program.return_type != spec.output:
        errors.append("return type mismatch")
    return errors


def _bvps_type_errors(program: bvps_ast.Program) -> list[str]:
    env_types = {name: type_name for name, type_name in program.params}
    try:
        inferred = _bvps_infer_type(program.body, env_types)
    except Exception as exc:
        return [f"type inference failed: {exc}"]
    if inferred != program.return_type:
        return [f"body type mismatch: {inferred} != {program.return_type}"]
    return []


def _bvps_op_errors(program: bvps_ast.Program) -> list[str]:
    ops: set[str] = set()
    _bvps_collect_ops(program.body, ops)
    invalid = sorted(op for op in ops if op not in BVPS_ALLOWED_OPS)
    if invalid:
        return [f"invalid ops: {', '.join(invalid)}"]
    return []


def _bvps_program_mismatch_errors(
    solution: dict[str, Any], pretty: str, ast_hash: str
) -> list[str]:
    errors: list[str] = []
    if "program_pretty" in solution and solution["program_pretty"] != pretty:
        errors.append("program_pretty mismatch")
    if "program_hash" in solution and solution["program_hash"] != ast_hash:
        errors.append("program_hash mismatch")
    return errors


def _bvps_collect_ops(expr: bvps_ast.Expr, ops: set[str]) -> None:
    if isinstance(expr, bvps_ast.BinOp):
        ops.add(expr.op)
        _bvps_collect_ops(expr.left, ops)
        _bvps_collect_ops(expr.right, ops)
    elif isinstance(expr, bvps_ast.IfThenElse):
        _bvps_collect_ops(expr.cond, ops)
        _bvps_collect_ops(expr.then_expr, ops)
        _bvps_collect_ops(expr.else_expr, ops)


def _bvps_infer_type(
    expr: bvps_ast.Expr, env: dict[str, bvps_types.TypeName]
) -> bvps_types.TypeName:
    if isinstance(expr, bvps_ast.IntConst):
        return "Int"
    if isinstance(expr, bvps_ast.BoolConst):
        return "Bool"
    if isinstance(expr, bvps_ast.Var):
        if expr.name not in env:
            raise ValueError(f"unknown var {expr.name}")
        return env[expr.name]
    if isinstance(expr, bvps_ast.BinOp):
        left = _bvps_infer_type(expr.left, env)
        right = _bvps_infer_type(expr.right, env)
        if expr.op in BVPS_INT_OPS:
            if left != "Int" or right != "Int":
                raise ValueError("int op with non-int operands")
            return "Int"
        if expr.op in {"lt", "gt"}:
            if left != "Int" or right != "Int":
                raise ValueError("comparison with non-int operands")
            return "Bool"
        if expr.op == "eq":
            if left != right:
                raise ValueError("eq operands type mismatch")
            return "Bool"
        raise ValueError(f"unknown op {expr.op}")
    if isinstance(expr, bvps_ast.IfThenElse):
        cond_type = _bvps_infer_type(expr.cond, env)
        if cond_type != "Bool":
            raise ValueError("if condition must be Bool")
        then_type = _bvps_infer_type(expr.then_expr, env)
        else_type = _bvps_infer_type(expr.else_expr, env)
        if then_type != else_type:
            raise ValueError("if branch type mismatch")
        return then_type
    raise ValueError("unknown expr type")


def _bvps_consequence_details(
    spec: bvps_types.Spec,
    program: bvps_ast.Program,
    *,
    seed: int,
    attempt: int,
) -> tuple[Status, dict[str, Any]]:
    rng = random.Random(seed)
    interpreter = BvpsInterpreter(step_budget=spec.bounds.step_budget)
    oracle_expr = _bvps_oracle_expr(spec)
    counterexample = None
    trials = max(1, int(spec.bounds.fuzz_trials))
    tested = 0
    variants_tested = 0

    for _ in range(trials):
        base_inputs = _bvps_random_inputs(spec, rng)
        tested += 1
        counterexample = _bvps_eval_input(
            program, spec, interpreter, oracle_expr, base_inputs, reason="fuzz"
        )
        if counterexample is not None:
            break
        for variant_inputs in _bvps_variants(spec, base_inputs):
            variants_tested += 1
            counterexample = _bvps_eval_input(
                program,
                spec,
                interpreter,
                oracle_expr,
                variant_inputs,
                reason="metamorphic",
            )
            if counterexample is not None:
                break
        if counterexample is not None:
            break

    status: Status = "PASS" if counterexample is None else "FAIL"
    details: dict[str, Any] = {
        "kind": "bvps",
        "attempt": attempt,
        "trials": trials,
        "tested": tested,
        "variants_tested": variants_tested,
        "oracle_used": oracle_expr is not None,
        "counterexample": counterexample,
    }
    return status, details


def _bvps_oracle_expr(spec: bvps_types.Spec) -> bvps_ast.Expr | None:
    if spec.oracle is None:
        return None
    return bvps_ast.expr_from_dict(spec.oracle)


def _bvps_eval_input(
    program: bvps_ast.Program,
    spec: bvps_types.Spec,
    interpreter: BvpsInterpreter,
    oracle_expr: bvps_ast.Expr | None,
    inputs: dict[str, bvps_types.Value],
    *,
    reason: str,
) -> dict[str, Any] | None:
    expected: bvps_types.Value | None = None
    if oracle_expr is not None:
        expected = _bvps_oracle_output(inputs, oracle_expr, interpreter, spec, program.params)
    try:
        output, _trace = interpreter.evaluate(program, inputs, trace=False)
    except Exception as exc:
        return {
            "input": inputs,
            "expected": expected if expected is not None else "violates generalized consistency",
            "output": None,
            "reason": "runtime_error",
            "note": str(exc),
        }
    if expected is not None and output != expected:
        return {
            "input": inputs,
            "expected": expected,
            "output": output,
            "reason": reason,
        }
    if expected is None and oracle_expr is None:
        return None
    return None


def _bvps_oracle_output(
    inputs: dict[str, bvps_types.Value],
    oracle_expr: bvps_ast.Expr,
    interpreter: BvpsInterpreter,
    spec: bvps_types.Spec,
    params: list[tuple[str, bvps_types.TypeName]] | None,
) -> bvps_types.Value:
    program_params = params or [(item.name, item.type) for item in spec.inputs]
    oracle_program = bvps_ast.Program(
        params=program_params,
        body=oracle_expr,
        return_type=spec.output,
    )
    output, _trace = interpreter.evaluate(oracle_program, inputs, trace=False)
    return output


def _arith_expression(task: TaskInput, signature: dict[str, Any]) -> str:
    expr = str(signature.get("expression") or "").strip()
    if expr:
        return expr
    data_expr = str(task.normalized.get("data", {}).get("expression", "")).strip()
    if data_expr:
        return data_expr
    prompt = str(task.normalized.get("prompt", "")).strip()
    for prefix in ("ARITH:", "arith:"):
        if prompt.startswith(prefix):
            return prompt[len(prefix) :].strip()
    return ""


def _bvps_random_inputs(spec: bvps_types.Spec, rng: random.Random) -> dict[str, bvps_types.Value]:
    inputs: dict[str, bvps_types.Value] = {}
    for item in spec.inputs:
        if item.type == "Int":
            inputs[item.name] = rng.randint(spec.bounds.int_min, spec.bounds.int_max)
        else:
            inputs[item.name] = rng.choice([True, False])
    return inputs


def _bvps_variants(
    spec: bvps_types.Spec, inputs: dict[str, bvps_types.Value]
) -> list[dict[str, bvps_types.Value]]:
    variants: list[dict[str, bvps_types.Value]] = []
    names = [item.name for item in spec.inputs]
    values = [inputs[name] for name in names]
    if len(names) > 1:
        perm_values = list(dict.fromkeys(itertools.permutations(values)))
        for perm in perm_values:
            if list(perm) == values:
                continue
            variants.append(dict(zip(names, perm, strict=False)))
    if spec.output == "Int" and spec.bounds.int_min < 0 < spec.bounds.int_max:
        flipped: dict[str, bvps_types.Value] = {}
        ok = True
        for item in spec.inputs:
            value = inputs[item.name]
            if item.type == "Int" and isinstance(value, int):
                flipped_value = -value
                if not (spec.bounds.int_min <= flipped_value <= spec.bounds.int_max):
                    ok = False
                    break
                flipped[item.name] = flipped_value
            else:
                flipped[item.name] = value
        if ok and flipped != inputs:
            variants.append(flipped)
    return variants
