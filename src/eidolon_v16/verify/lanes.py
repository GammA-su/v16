from __future__ import annotations

import logging
import random
from typing import Any, Literal

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps.dsl import program_from_dict
from eidolon_v16.bvps.interpreter import Interpreter
from eidolon_v16.bvps.synth import spec_function
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.ucr.models import Interpretation, LaneVerdict, TaskInput
from eidolon_v16.utils import safe_eval_int
from eidolon_v16.worldlab.gridworld import GridWorld
from eidolon_v16.worldlab.runner import run_rollout

logger = logging.getLogger(__name__)

Status = Literal["PASS", "FAIL", "BORDERLINE"]

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


def _required_field_errors(
    kind: str, solution: dict[str, Any], signature: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if kind == "arith":
        if "expression" not in solution:
            errors.append("missing solution.expression")
        if "output" not in solution:
            errors.append("missing solution.output")
        if solution.get("expression") != signature.get("expression"):
            errors.append("expression mismatch")
    elif kind == "list":
        if "program" not in solution:
            errors.append("missing solution.program")
        if "input" not in solution:
            errors.append("missing solution.input")
        if "output" not in solution:
            errors.append("missing solution.output")
        if "operation" in solution and solution.get("operation") != signature.get("operation"):
            errors.append("operation mismatch")
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
) -> LaneVerdict:
    logger.info("recompute lane start")
    kind = task.normalized.get("kind", "unknown")
    status: Status = "FAIL"
    details: dict[str, Any] = {"kind": kind}
    if kind == "arith":
        expr = str(task.normalized.get("data", {}).get("expression", "0"))
        computed = safe_eval_int(expr)
        expected = solution.get("output")
        status = "PASS" if computed == expected else "FAIL"
        details.update({"expression": expr, "computed": computed, "expected": expected})
    elif kind == "list":
        program = program_from_dict(solution["program"])
        interpreter = Interpreter(step_limit=2000)
        output, trace = interpreter.run(program, [solution["input"]])
        expected = solution.get("output")
        status = "PASS" if output == expected else "FAIL"
        details.update({"computed": output, "expected": expected, "trace": trace})
    elif kind == "world":
        actions = solution.get("actions", [])
        world = GridWorld(width=3, height=3, goal=(2, 2))
        rollout = run_rollout(world, actions, seed=0)
        status = "PASS" if rollout["done"] else "FAIL"
        details.update({"rollout": rollout})
    else:
        details["error"] = "unsupported kind"
    evidence = store.put_json(details, artifact_type="lane_recompute", producer="verify")
    logger.info("recompute lane status=%s", status)
    return LaneVerdict(lane="recompute", status=status, evidence=[evidence])


def run_translation(
    task: TaskInput,
    chosen: Interpretation,
    solution: dict[str, Any],
    store: ArtifactStore,
    seed: int,
) -> LaneVerdict:
    logger.info("translation lane start")
    kernel = StubKernel()
    signature = task_signature(task)
    kind = signature.get("kind", "unknown")
    errors = _required_field_errors(str(kind), solution, signature)

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
    evidence = store.put_json(
        evidence_payload,
        artifact_type="lane_translation",
        producer="verify",
    )
    logger.info("translation lane status=%s", status)
    return LaneVerdict(lane="translation", status=status, evidence=[evidence])


def run_consequence(
    task: TaskInput,
    solution: dict[str, Any],
    store: ArtifactStore,
    seed: int,
) -> LaneVerdict:
    logger.info("consequence lane start")
    kind = task.normalized.get("kind", "unknown")
    status: Status = "FAIL"
    details: dict[str, Any] = {"kind": kind}
    rng = random.Random(seed)
    if kind == "arith":
        expr = str(task.normalized.get("data", {}).get("expression", "0"))
        computed = safe_eval_int(expr)
        expected = solution.get("output")
        status = "PASS" if computed == expected else "FAIL"
        details.update({"expression": expr, "computed": computed, "expected": expected})
    elif kind == "list":
        program = program_from_dict(solution["program"])
        interpreter = Interpreter(step_limit=2000)
        operation = str(task.normalized.get("data", {}).get("operation", "sum"))
        spec = spec_function(operation)
        counterexample = None
        for _ in range(10):
            length = rng.randint(0, 5)
            sample = [rng.randint(-3, 6) for _ in range(length)]
            expected = spec(sample)
            output, _trace = interpreter.run(program, [sample])
            if output != expected:
                counterexample = {"input": sample, "expected": expected, "output": output}
                break
        status = "PASS" if counterexample is None else "FAIL"
        details.update({"operation": operation, "counterexample": counterexample})
    elif kind == "world":
        actions = solution.get("actions", [])
        world = GridWorld(width=3, height=3, goal=(2, 2))
        rollout = run_rollout(world, actions, seed=seed)
        status = "PASS" if rollout["done"] else "FAIL"
        details.update({"rollout": rollout})
    else:
        details["error"] = "unsupported kind"
    evidence = store.put_json(details, artifact_type="lane_consequence", producer="verify")
    logger.info("consequence lane status=%s", status)
    return LaneVerdict(lane="consequence", status=status, evidence=[evidence])


def run_anchors(lanes: list[LaneVerdict], store: ArtifactStore) -> LaneVerdict:
    logger.info("anchors lane start")
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
    logger.info("anchors lane status=%s", status)
    return LaneVerdict(lane="anchors", status=status, evidence=[evidence])
