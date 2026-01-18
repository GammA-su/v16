from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps.synth import spec_function
from eidolon_v16.config import AppConfig
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.runtime import initialize_runtime
from eidolon_v16.ucr.canonical import sha256_bytes
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.utils import safe_eval_arith
from eidolon_v16.worldlab.gridworld import GridWorld

logger = logging.getLogger(__name__)

_CANARY = "CANARY-DO-NOT-EMIT"


@dataclass(frozen=True)
class SuiteGenerator:
    kind: str
    weight: int


@dataclass(frozen=True)
class SuiteSpec:
    suite_name: str
    generators: list[SuiteGenerator]


@dataclass(frozen=True)
class SealedEvalRun:
    report_path: Path
    commitment_hash: str
    seed_hex: str | None


def run_sealed_eval(
    config: AppConfig,
    suite_path: Path,
    n: int,
    seed: int | None,
    reveal_seed: bool,
) -> SealedEvalRun:
    suite_bytes = suite_path.read_bytes()
    suite = _load_suite_yaml(suite_bytes, suite_path)
    seed_bytes, seed_int = _select_seed(seed)
    commitment_hash = sha256_bytes(seed_bytes + suite_bytes + str(n).encode("utf-8"))
    kernel_seed = seed_int if reveal_seed else 0
    mode = ModeConfig(seed=kernel_seed)
    initialize_runtime(
        cpu_threads=mode.cpu_threads,
        use_gpu=mode.use_gpu,
        gpu_id=mode.gpu_id,
        logger=logger,
    )

    store = ArtifactStore(config.paths.artifact_store)
    controller = EpisodeController(config=config)
    rng = random.Random(seed_int)

    tasks_with_expected = _generate_tasks(suite, rng, n)
    tasks = [task for task, _expected in tasks_with_expected]
    _inject_canary(tasks)

    tasks_ref = store.put_json(tasks, artifact_type="sealed_tasks", producer="eval")

    results: list[dict[str, Any]] = []
    canary_hits = 0
    pass_count = 0
    fail_count = 0

    for idx, (raw, expected) in enumerate(tasks_with_expected, start=1):
        logger.info("sealed eval task %s/%s", idx, len(tasks_with_expected))
        task = TaskInput.from_raw(raw)
        result = controller.run(task, mode)
        ucr_payload = json.loads(Path(result.ucr_path).read_text())
        final_result = str(ucr_payload.get("final_result", ""))
        verdict = "pass" if final_result == _expected_to_result(expected) else "fail"
        if verdict == "pass":
            pass_count += 1
        else:
            fail_count += 1

        if _CANARY in final_result:
            canary_hits += 1

        results.append(
            {
                "task_id": task.normalized["task_id"],
                "ucr_hash": result.ucr_hash,
                "ucr_path": str(result.ucr_path),
                "verdict": verdict,
            }
        )

    report: dict[str, Any] = {
        "suite_name": suite.suite_name,
        "n": n,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "canary_hits": canary_hits,
        "commitment_hash": commitment_hash,
        "results": results,
        "sealed_tasks_artifact": {
            "hash": tasks_ref.hash,
            "type": tasks_ref.type,
            "media_type": tasks_ref.media_type,
            "size": tasks_ref.size,
        },
    }
    seed_hex = seed_bytes.hex() if reveal_seed else None
    if seed_hex is not None:
        report["seed_hex"] = seed_hex

    report_ref = store.put_json(report, artifact_type="eval_sealed_report", producer="eval")
    report_path = store.path_for_hash(report_ref.hash)
    logger.info("sealed eval complete report=%s commitment=%s", report_path, commitment_hash)
    return SealedEvalRun(
        report_path=report_path,
        commitment_hash=commitment_hash,
        seed_hex=seed_hex,
    )


def _select_seed(seed: int | None) -> tuple[bytes, int]:
    if seed is None:
        seed_bytes = os.urandom(16)
        seed_int = int.from_bytes(seed_bytes, "big")
        return seed_bytes, seed_int
    seed_bytes = str(seed).encode("utf-8")
    return seed_bytes, seed


def _expected_to_result(expected: object) -> str:
    return f"result={expected}"


def _load_suite_yaml(data: bytes, path: Path) -> SuiteSpec:
    payload = data.lstrip()
    if payload.startswith(b"{"):
        raw = json.loads(payload.decode("utf-8"))
    else:
        raw = _parse_simple_yaml(payload.decode("utf-8"))
    suite_name = str(raw.get("suite_name") or raw.get("name") or path.stem)
    generators_raw = raw.get("generators", [])
    generators: list[SuiteGenerator] = []
    for entry in generators_raw:
        kind = str(entry.get("kind", "arith"))
        weight = int(entry.get("weight", 1))
        generators.append(SuiteGenerator(kind=kind, weight=weight))
    if not generators:
        generators = [
            SuiteGenerator(kind="arith", weight=1),
            SuiteGenerator(kind="list", weight=1),
            SuiteGenerator(kind="world", weight=1),
        ]
    return SuiteSpec(suite_name=suite_name, generators=generators)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_list: list[dict[str, Any]] | None = None
    current_key: str | None = None
    current_item: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_key is None:
                raise ValueError("invalid suite yaml: list item without parent key")
            if current_key == "seeds":
                if current_list is None:
                    current_list = []
                    result[current_key] = current_list
                current_list.append(_parse_value(line[4:].strip()))
                current_item = None
                continue
            if current_item is not None and current_list is not None:
                current_list.append(current_item)
            current_item = {}
            item_content = line[4:].strip()
            if item_content:
                key, value = _split_kv(item_content)
                current_item[key] = _parse_value(value)
            continue
        if line.startswith("    "):
            if current_item is None:
                raise ValueError("invalid suite yaml: indented item without list")
            key, value = _split_kv(line.strip())
            current_item[key] = _parse_value(value)
            continue
        if current_item is not None and current_list is not None:
            current_list.append(current_item)
            current_item = None
        key, value = _split_kv(line)
        if value == "":
            current_key = key
            current_list = []
            result[key] = current_list
        else:
            result[key] = _parse_value(value)
            current_key = None
            current_list = None

    if current_item is not None and current_list is not None:
        current_list.append(current_item)
    return result


def _split_kv(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"invalid suite yaml line: {line}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _parse_value(value: str) -> Any:
    if value == "":
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _generate_tasks(
    suite: SuiteSpec,
    rng: random.Random,
    n: int,
) -> list[tuple[dict[str, Any], object]]:
    generators = suite.generators
    total_weight = sum(gen.weight for gen in generators)
    tasks: list[tuple[dict[str, Any], object]] = []
    for idx in range(n):
        pick = rng.uniform(0, total_weight)
        choice = generators[-1]
        acc = 0.0
        for gen in generators:
            acc += gen.weight
            if pick <= acc:
                choice = gen
                break
        task, expected = _generate_task(choice.kind, rng, idx)
        tasks.append((task, expected))
    return tasks


def _generate_task(kind: str, rng: random.Random, idx: int) -> tuple[dict[str, Any], object]:
    if kind == "arith":
        a = rng.randint(1, 9)
        b = rng.randint(1, 9)
        c = rng.randint(1, 5)
        expr = f"{a} + {b} * {c}"
        expected_arith = safe_eval_arith(expr)
        task = {
            "task_id": f"arith-sealed-{idx}",
            "kind": "arith",
            "prompt": f"Solve the expression: {expr}",
            "data": {"expression": expr},
        }
        return task, expected_arith
    if kind == "list":
        op = rng.choice(["sum", "max", "reverse", "is_sorted"])
        values = [rng.randint(-3, 6) for _ in range(rng.randint(0, 5))]
        expected_list = spec_function(op)(values)
        task = {
            "task_id": f"list-sealed-{idx}",
            "kind": "list",
            "prompt": f"Compute {op} for the list.",
            "data": {"operation": op, "input": values},
        }
        return task, expected_list
    if kind == "world":
        width = 3
        height = 3
        goal = (2, 2)
        expected_world = _plan_world_actions(width, height, goal)
        task = {
            "task_id": f"world-sealed-{idx}",
            "kind": "world",
            "prompt": "Reach the goal in the grid.",
            "data": {"goal": list(goal), "width": width, "height": height},
        }
        return task, expected_world
    raise ValueError(f"unknown generator kind: {kind}")


def _plan_world_actions(width: int, height: int, goal: tuple[int, int]) -> list[str]:
    world = GridWorld(width=width, height=height, goal=goal)
    actions: list[str] = []
    world.reset(seed=0)
    while world.agent != world.goal:
        ax, ay = world.agent
        gx, gy = world.goal
        if ax < gx:
            actions.append("right")
            world.step("right")
            continue
        if ay < gy:
            actions.append("down")
            world.step("down")
            continue
        if ax > gx:
            actions.append("left")
            world.step("left")
            continue
        if ay > gy:
            actions.append("up")
            world.step("up")
            continue
    return actions


def _inject_canary(tasks: list[dict[str, Any]]) -> None:
    for idx, task in enumerate(tasks):
        if idx % 10 == 0:
            task["prompt"] = f"{task.get('prompt','')} {_CANARY}".strip()
            task.setdefault("data", {})["canary"] = _CANARY
