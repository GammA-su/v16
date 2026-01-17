from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import AppConfig
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SuiteTask:
    name: str
    path: Path


@dataclass(frozen=True)
class SuiteSpec:
    suite_name: str
    tasks: list[SuiteTask]
    seeds: list[int]


@dataclass(frozen=True)
class SuiteReport:
    report_path: Path


def run_suite(config: AppConfig, suite_path: Path) -> SuiteReport:
    suite_spec = _load_suite_yaml(suite_path.read_bytes(), suite_path)
    store = ArtifactStore(config.paths.artifact_store)
    controller = EpisodeController(config=config)

    results: list[dict[str, Any]] = []
    for seed in suite_spec.seeds:
        logger.info("suite run seed=%s", seed)
        for task_entry in suite_spec.tasks:
            raw = json.loads(task_entry.path.read_text())
            task = TaskInput.from_raw(raw)
            result = controller.run(task, ModeConfig(seed=seed, use_gpu=False))
            payload = json.loads(result.ucr_path.read_text())
            lane_statuses = {lane["lane"]: lane["status"] for lane in payload["verification"]}
            results.append(
                {
                    "task": task_entry.name,
                    "seed": seed,
                    "run_dir": str(result.ucr_path.parent),
                    "ucr_hash": result.ucr_hash,
                    "final_result": payload.get("final_result", ""),
                    "lane_statuses": lane_statuses,
                }
            )

    report: dict[str, Any] = {
        "suite_name": suite_spec.suite_name,
        "tasks": [task.name for task in suite_spec.tasks],
        "seeds": suite_spec.seeds,
        "total_runs": len(results),
        "runs": results,
    }
    report_ref = store.put_json(report, artifact_type="eval_suite_report", producer="eval")
    report_path = store.path_for_hash(report_ref.hash)
    logger.info("suite complete report=%s", report_path)
    return SuiteReport(report_path=report_path)


def _load_suite_yaml(data: bytes, path: Path) -> SuiteSpec:
    payload = data.lstrip()
    if payload.startswith(b"{"):
        raw = json.loads(payload.decode("utf-8"))
    else:
        raw = _parse_simple_yaml(payload.decode("utf-8"))
    suite_name = str(raw.get("suite_name") or raw.get("name") or path.stem)
    tasks_raw = raw.get("tasks", [])
    if not isinstance(tasks_raw, list):
        raise ValueError("suite tasks must be a list")
    tasks: list[SuiteTask] = []
    for index, entry in enumerate(tasks_raw):
        if not isinstance(entry, dict):
            raise ValueError("suite task entry must be a mapping")
        name = str(entry.get("name") or entry.get("task") or f"task-{index}")
        raw_path = entry.get("path")
        if raw_path is None:
            raise ValueError(f"task {name} missing path")
        task_path = Path(str(raw_path))
        if task_path.is_absolute():
            resolved = task_path
        else:
            candidate = (path.parent / task_path).resolve()
            if candidate.exists():
                resolved = candidate
            else:
                fallback = (Path.cwd() / task_path).resolve()
                resolved = fallback if fallback.exists() else candidate
        if not resolved.exists():
            raise FileNotFoundError(f"task file not found: {task_path}")
        tasks.append(SuiteTask(name=name, path=resolved))
    seeds_raw = raw.get("seeds") or [0]
    seeds: list[int] = []
    if isinstance(seeds_raw, list):
        for value in seeds_raw:
            seeds.append(int(value))
    else:
        seeds.append(int(seeds_raw))
    if not seeds:
        seeds = [0]
    return SuiteSpec(suite_name=suite_name, tasks=tasks, seeds=seeds)


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
            item_content = line[4:].strip()
            if current_key == "seeds":
                if current_list is None:
                    current_list = []
                    result[current_key] = current_list
                current_list.append(_parse_value(item_content))
                current_item = None
                continue
            if current_item is not None and current_list is not None:
                current_list.append(current_item)
            current_item = {}
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
