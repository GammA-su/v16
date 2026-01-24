from __future__ import annotations

from typing import Any


def get_field(payload: dict[str, Any], dotted_path: str) -> Any | None:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current


def infer_task(payload: dict[str, Any]) -> str | None:
    for key in ("task", "task_id", "task_name", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for dotted in ("spec.task", "spec.name", "spec.task_id"):
        value = get_field(payload, dotted)
        if isinstance(value, str) and value.strip():
            return value
    for dotted in ("item.task", "item.name", "item.id", "item.task_id"):
        value = get_field(payload, dotted)
        if isinstance(value, str) and value.strip():
            return value
    return None


def infer_seed(payload: dict[str, Any]) -> int | str | None:
    for dotted in ("seed", "config.seed", "spec.seed", "item.seed"):
        value = get_field(payload, dotted)
        if value is not None:
            return value
    return None
