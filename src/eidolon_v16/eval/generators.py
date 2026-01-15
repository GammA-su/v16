from __future__ import annotations

import random
from typing import Any

_CANARY = "CANARY-DO-NOT-EMIT"


def generate_open_tasks(n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    tasks: list[dict[str, Any]] = []
    for idx in range(n):
        family = idx % 3
        if family == 0:
            tasks.append(_arith_task_open(rng, idx))
        elif family == 1:
            tasks.append(_list_task_open(rng, idx))
        else:
            tasks.append(_world_task_open(rng, idx))
    _inject_canary(tasks)
    return tasks


def generate_sealed_tasks(n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 999)
    tasks: list[dict[str, Any]] = []
    for idx in range(n):
        family = idx % 3
        if family == 0:
            tasks.append(_arith_task_sealed(rng, idx))
        elif family == 1:
            tasks.append(_list_task_sealed(rng, idx))
        else:
            tasks.append(_world_task_sealed(rng, idx))
    _inject_canary(tasks)
    return tasks


def _arith_task_open(rng: random.Random, idx: int) -> dict[str, Any]:
    a = rng.randint(0, 9)
    b = rng.randint(0, 9)
    c = rng.randint(1, 5)
    expr = f"{a} + {b} * {c}"
    return {
        "task_id": f"arith-open-{idx}",
        "kind": "arith",
        "prompt": f"Compute {expr}",
        "data": {"expression": expr},
    }


def _arith_task_sealed(rng: random.Random, idx: int) -> dict[str, Any]:
    a = rng.randint(0, 9)
    b = rng.randint(0, 9)
    c = rng.randint(1, 5)
    expr = f"({a} + {b}) * {c}"
    return {
        "task_id": f"arith-sealed-{idx}",
        "kind": "arith",
        "prompt": f"What is the value of {expr}?",
        "data": {"expression": expr},
    }


def _list_task_open(rng: random.Random, idx: int) -> dict[str, Any]:
    op = rng.choice(["sum", "max", "reverse", "is_sorted"])
    values = [rng.randint(-3, 6) for _ in range(rng.randint(0, 5))]
    return {
        "task_id": f"list-open-{idx}",
        "kind": "list",
        "prompt": f"Compute {op} for the list.",
        "data": {"operation": op, "input": values},
    }


def _list_task_sealed(rng: random.Random, idx: int) -> dict[str, Any]:
    op = rng.choice(["sum", "max", "reverse", "is_sorted"])
    values = [rng.randint(-3, 6) for _ in range(rng.randint(0, 5))]
    return {
        "task_id": f"list-sealed-{idx}",
        "kind": "list",
        "prompt": f"Given list {values}, return {op}.",
        "data": {"operation": op, "input": values},
    }


def _world_task_open(rng: random.Random, idx: int) -> dict[str, Any]:
    _ = rng
    return {
        "task_id": f"world-open-{idx}",
        "kind": "world",
        "prompt": "Reach the goal in the grid.",
        "data": {"goal": [2, 2], "width": 3, "height": 3},
    }


def _world_task_sealed(rng: random.Random, idx: int) -> dict[str, Any]:
    _ = rng
    return {
        "task_id": f"world-sealed-{idx}",
        "kind": "world",
        "prompt": "Navigate to the target cell on the board.",
        "data": {"goal": [2, 2], "width": 3, "height": 3},
    }


def _inject_canary(tasks: list[dict[str, Any]]) -> None:
    for idx, task in enumerate(tasks):
        if idx % 10 == 0:
            task["prompt"] = f"{task.get('prompt','')} {_CANARY}".strip()
            task.setdefault("data", {})["canary"] = _CANARY
