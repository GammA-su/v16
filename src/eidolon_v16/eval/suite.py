from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import cache as bvps_cache
from eidolon_v16.config import AppConfig
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.canonical import canonical_json_bytes
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


def run_suite(config: AppConfig, suite_path: Path, out_dir: Path | None = None) -> SuiteReport:
    suite_spec = _load_suite_yaml(suite_path.read_bytes(), suite_path)
    store = ArtifactStore(config.paths.artifact_store)
    suite_meta: dict[str, Any] = {}
    bvps_cache_entries: dict[tuple[str, str, int], dict[str, Any]] = {}
    if (
        bvps_cache.persist_enabled()
        and os.getenv("EIDOLON_BVPS_PERSIST_PRELOAD", "").strip() == "1"
    ):
        persist_store = bvps_cache.persist_store()
        cache_entries, stats = bvps_cache.preload_persistent_cache(persist_store)
        bvps_cache_entries.update(cache_entries)
        suite_meta = {
            "bvps_persist_preload_ms": stats.preload_ms,
            "bvps_persist_preload_entries": stats.entries,
            "bvps_persist_preload_errors": stats.errors,
        }
    store.set_manifest_flush_mode("per_suite")
    controller = EpisodeController(config=config, bvps_cache=bvps_cache_entries)

    results: list[dict[str, Any]] = []
    per_task_totals: dict[str, dict[str, Any]] = {}
    total_ms_values: list[int] = []
    verify_phase_values: list[int] = []
    overhead_values: list[int] = []
    overhead_startup_values: list[int] = []
    overhead_postcapsule_values: list[int] = []
    overhead_residual_values: list[int] = []
    postsolve_detail_values: dict[str, list[int]] = {}
    artifact_plan_detail_values: dict[str, list[int]] = {}
    manifest_detail_values: dict[str, list[int]] = {}
    lane_ms_sum: dict[str, int] = {}
    verify_artifact_values: list[int] = []
    verify_admission_values: list[int] = []
    verify_run_dir_write_values: list[int] = []
    verify_json_serialize_values: list[int] = []
    verify_store_manifest_values: list[int] = []
    solve_model_values: list[int] = []
    solve_cache_lookup_values: list[int] = []
    solve_other_values: list[int] = []
    verify_checks_values: dict[str, list[int]] = {}
    for seed in suite_spec.seeds:
        logger.info("suite run seed=%s", seed)
        for task_entry in suite_spec.tasks:
            raw = json.loads(task_entry.path.read_text())
            task = TaskInput.from_raw(raw)
            result = controller.run(
                task,
                ModeConfig(seed=seed, use_gpu=False),
                store=store,
            )
            payload = json.loads(result.ucr_path.read_text())
            verification = payload.get("verification", [])
            if not isinstance(verification, list):
                verification = []
            costs = payload.get("costs", {})
            if not isinstance(costs, dict):
                costs = {}
            total_ms = _as_int(costs.get("total_ms"))
            lane_verdicts = payload.get("lane_verdicts", {})
            if not isinstance(lane_verdicts, dict):
                lane_verdicts = {}
            if not lane_verdicts:
                lane_verdicts = _lane_verdicts_from_list(verification)
            if not lane_verdicts:
                witness_verification = _load_witness_verification(result.ucr_path.parent)
                if witness_verification:
                    verification = witness_verification
                    lane_verdicts = _lane_verdicts_from_list(verification)
            lane_verdicts = _normalize_lane_verdicts(lane_verdicts)
            lane_statuses = _lane_statuses_from_verdicts(lane_verdicts)
            lane_ms = _lane_ms_from_verdicts(lane_verdicts)
            if not lane_ms:
                lane_ms = _normalize_lane_ms(costs.get("lane_ms", {}))
            phase_ms = costs.get("phase_ms", {})
            if not isinstance(phase_ms, dict):
                phase_ms = {}
            if total_ms:
                total_ms_values.append(total_ms)
            if "verify" in phase_ms:
                verify_phase_values.append(_as_int(phase_ms.get("verify")))
            overhead_ms = _as_int(costs.get("overhead_ms"))
            if "overhead_ms" in costs:
                overhead_values.append(overhead_ms)
            _merge_lane_ms(lane_ms_sum, lane_ms)
            solve_breakdown = costs.get("solve_breakdown_ms", {})
            if not isinstance(solve_breakdown, dict):
                solve_breakdown = {}
            solve_model_ms = _as_int(solve_breakdown.get("solve_model_ms"))
            solve_cache_lookup_ms = _as_int(
                solve_breakdown.get("solve_bvps_cache_lookup_ms")
            )
            solve_other_ms = _as_int(solve_breakdown.get("solve_other_ms"))
            if "solve_model_ms" in solve_breakdown:
                solve_model_values.append(solve_model_ms)
            if "solve_bvps_cache_lookup_ms" in solve_breakdown:
                solve_cache_lookup_values.append(solve_cache_lookup_ms)
            if "solve_other_ms" in solve_breakdown:
                solve_other_values.append(solve_other_ms)
            solve_stats = costs.get("solve_bvps_stats", {})
            if not isinstance(solve_stats, dict):
                solve_stats = {}
            bvps_cache_meta = costs.get("bvps_cache", {})
            if not isinstance(bvps_cache_meta, dict):
                bvps_cache_meta = {}
            bvps_cache_state = costs.get("bvps_cache_state")
            if not isinstance(bvps_cache_state, str):
                bvps_cache_state = ""
            if not bvps_cache_state and bvps_cache_meta:
                if "state" in bvps_cache_meta:
                    bvps_cache_state = str(bvps_cache_meta.get("state") or "")
                else:
                    hit = bool(bvps_cache_meta.get("hit"))
                    scope = str(bvps_cache_meta.get("scope") or "none")
                    bvps_cache_state = f"hit:{scope}" if hit else "miss:none"
            bvps_ids = costs.get("bvps_ids", {})
            if not isinstance(bvps_ids, dict):
                bvps_ids = {}
            bvps_fastpath = costs.get("bvps_fastpath")
            spec_hash = bvps_ids.get("spec_hash")
            macros_hash = bvps_ids.get("macros_hash")
            program_hash = bvps_ids.get("program_hash")
            verify_breakdown = costs.get("verify_breakdown_ms", {})
            if not isinstance(verify_breakdown, dict):
                verify_breakdown = {}
            verify_artifact_ms = _as_int(verify_breakdown.get("verify_artifact_ms"))
            verify_admission_ms = _as_int(verify_breakdown.get("verify_admission_ms"))
            verify_run_dir_write_ms = _as_int(
                verify_breakdown.get("verify_run_dir_write_ms")
            )
            verify_json_serialize_ms = _as_int(
                verify_breakdown.get("verify_json_serialize_ms")
            )
            store_breakdown = verify_breakdown.get("verify_store_ms", {})
            if isinstance(store_breakdown, dict):
                verify_store_manifest_values.append(
                    _as_int(store_breakdown.get("manifest_ms"))
                )
            if "verify_artifact_ms" in verify_breakdown:
                verify_artifact_values.append(verify_artifact_ms)
            if "verify_admission_ms" in verify_breakdown:
                verify_admission_values.append(verify_admission_ms)
            if "verify_run_dir_write_ms" in verify_breakdown:
                verify_run_dir_write_values.append(verify_run_dir_write_ms)
            if "verify_json_serialize_ms" in verify_breakdown:
                verify_json_serialize_values.append(verify_json_serialize_ms)
            overhead_breakdown = costs.get("overhead_breakdown_ms", {})
            if not isinstance(overhead_breakdown, dict):
                overhead_breakdown = {}
            postsolve_detail = overhead_breakdown.get("postsolve_detail_ms", {})
            if not isinstance(postsolve_detail, dict):
                postsolve_detail = {}
            artifact_plan_detail = overhead_breakdown.get(
                "postsolve_artifact_plan_detail_ms", {}
            )
            if not isinstance(artifact_plan_detail, dict):
                artifact_plan_detail = {}
            manifest_detail = overhead_breakdown.get("verify_store_manifest_detail_ms", {})
            if not isinstance(manifest_detail, dict):
                manifest_detail = {}
            overhead_startup_ms = _as_int(overhead_breakdown.get("overhead_startup_ms"))
            overhead_postcapsule_ms = _as_int(
                overhead_breakdown.get("overhead_postcapsule_ms")
            )
            overhead_residual_ms = _as_int(
                overhead_breakdown.get("overhead_residual_ms")
            )
            if "overhead_startup_ms" in overhead_breakdown:
                overhead_startup_values.append(overhead_startup_ms)
            if "overhead_postcapsule_ms" in overhead_breakdown:
                overhead_postcapsule_values.append(overhead_postcapsule_ms)
            if "overhead_residual_ms" in overhead_breakdown:
                overhead_residual_values.append(overhead_residual_ms)
            for key, value in postsolve_detail.items():
                postsolve_detail_values.setdefault(str(key), []).append(_as_int(value))
            for key, value in artifact_plan_detail.items():
                artifact_plan_detail_values.setdefault(str(key), []).append(_as_int(value))
            for key, value in manifest_detail.items():
                manifest_detail_values.setdefault(str(key), []).append(_as_int(value))
            verify_checks = costs.get("verify_checks_ms", {})
            if isinstance(verify_checks, dict):
                for key, value in verify_checks.items():
                    verify_checks_values.setdefault(str(key), []).append(_as_int(value))
            per_task = per_task_totals.setdefault(
                task_entry.name,
                {"task": task_entry.name, "runs": 0, "total_ms_sum": 0, "lane_ms_sum": {}},
            )
            per_task["runs"] += 1
            per_task["total_ms_sum"] += total_ms
            _merge_lane_ms(per_task["lane_ms_sum"], lane_ms)
            results.append(
                {
                    "task": task_entry.name,
                    "seed": seed,
                    "run_dir": str(result.ucr_path.parent),
                    "ucr_hash": result.ucr_hash,
                    "final_result": payload.get("final_result", ""),
                    "lane_statuses": lane_statuses,
                    "lane_verdicts": lane_verdicts,
                    "total_ms": total_ms,
                    "lane_ms": lane_ms,
                    "phase_ms": phase_ms,
                    "solve_breakdown_ms": solve_breakdown,
                    "solve_bvps_stats": solve_stats,
                    "bvps_cache": bvps_cache_state,
                    "bvps_cache_meta": bvps_cache_meta,
                    "bvps_ids": bvps_ids,
                    "bvps_fastpath": bvps_fastpath,
                    "spec_hash": spec_hash,
                    "macros_hash": macros_hash,
                    "program_hash": program_hash,
                    "verify_breakdown_ms": verify_breakdown,
                    "verify_checks_ms": verify_checks,
                    "overhead_ms": overhead_ms,
                    "overhead_breakdown_ms": overhead_breakdown,
                }
            )

    total_ms_sum = sum(total_ms_values)
    total_ms_mean = int(total_ms_sum / len(total_ms_values)) if total_ms_values else 0
    total_ms_p95 = _percentile(total_ms_values, 0.95)
    total_ms_p99 = _percentile(total_ms_values, 0.99)
    total_ms_max = max(total_ms_values) if total_ms_values else 0
    verify_artifact_sum = sum(verify_artifact_values)
    verify_artifact_mean = (
        int(verify_artifact_sum / len(verify_artifact_values))
        if verify_artifact_values
        else 0
    )
    verify_admission_sum = sum(verify_admission_values)
    verify_admission_mean = (
        int(verify_admission_sum / len(verify_admission_values))
        if verify_admission_values
        else 0
    )
    verify_run_dir_write_sum = sum(verify_run_dir_write_values)
    verify_run_dir_write_mean = (
        int(verify_run_dir_write_sum / len(verify_run_dir_write_values))
        if verify_run_dir_write_values
        else 0
    )
    verify_json_serialize_sum = sum(verify_json_serialize_values)
    verify_json_serialize_mean = (
        int(verify_json_serialize_sum / len(verify_json_serialize_values))
        if verify_json_serialize_values
        else 0
    )
    solve_model_sum = sum(solve_model_values)
    solve_model_mean = (
        int(solve_model_sum / len(solve_model_values)) if solve_model_values else 0
    )
    solve_cache_lookup_sum = sum(solve_cache_lookup_values)
    solve_cache_lookup_mean = (
        int(solve_cache_lookup_sum / len(solve_cache_lookup_values))
        if solve_cache_lookup_values
        else 0
    )
    solve_other_sum = sum(solve_other_values)
    solve_other_mean = (
        int(solve_other_sum / len(solve_other_values)) if solve_other_values else 0
    )
    report: dict[str, Any] = {
        "suite_name": suite_spec.suite_name,
        "tasks": [task.name for task in suite_spec.tasks],
        "seeds": suite_spec.seeds,
        "total_runs": len(results),
        "suite_meta": suite_meta,
        "per_task": sorted(per_task_totals.values(), key=lambda item: item["task"]),
        "metrics": {
            "store_manifest_flush_mode": store.manifest_flush_mode(),
            "total_ms_sum": total_ms_sum,
            "total_ms_mean": total_ms_mean,
            "total_ms_p95": total_ms_p95,
            "total_ms_p99": total_ms_p99,
            "total_ms_max": total_ms_max,
            "lane_ms_sum": lane_ms_sum,
            "verify_artifact_ms_sum": verify_artifact_sum,
            "verify_artifact_ms_mean": verify_artifact_mean,
            "verify_artifact_ms_p95": _percentile(verify_artifact_values, 0.95),
            "verify_admission_ms_sum": verify_admission_sum,
            "verify_admission_ms_mean": verify_admission_mean,
            "verify_admission_ms_p95": _percentile(verify_admission_values, 0.95),
            "verify_run_dir_write_ms_sum": verify_run_dir_write_sum,
            "verify_run_dir_write_ms_mean": verify_run_dir_write_mean,
            "verify_run_dir_write_ms_p95": _percentile(verify_run_dir_write_values, 0.95),
            "verify_json_serialize_ms_sum": verify_json_serialize_sum,
            "verify_json_serialize_ms_mean": verify_json_serialize_mean,
            "verify_json_serialize_ms_p95": _percentile(verify_json_serialize_values, 0.95),
            "verify_store_manifest_ms_p95": _percentile(
                verify_store_manifest_values, 0.95
            ),
            "verify_store_manifest_ms_p99": _percentile(
                verify_store_manifest_values, 0.99
            ),
            "verify_store_manifest_ms_max": max(verify_store_manifest_values)
            if verify_store_manifest_values
            else 0,
            "verify_phase_ms_p99": _percentile(verify_phase_values, 0.99),
            "verify_phase_ms_max": max(verify_phase_values) if verify_phase_values else 0,
            "overhead_ms_p95": _percentile(overhead_values, 0.95),
            "overhead_ms_p99": _percentile(overhead_values, 0.99),
            "overhead_ms_max": max(overhead_values) if overhead_values else 0,
            "overhead_startup_ms_p95": _percentile(overhead_startup_values, 0.95),
            "overhead_startup_ms_p99": _percentile(overhead_startup_values, 0.99),
            "overhead_startup_ms_max": max(overhead_startup_values)
            if overhead_startup_values
            else 0,
            "overhead_postcapsule_ms_p95": _percentile(overhead_postcapsule_values, 0.95),
            "overhead_postcapsule_ms_p99": _percentile(overhead_postcapsule_values, 0.99),
            "overhead_postcapsule_ms_max": max(overhead_postcapsule_values)
            if overhead_postcapsule_values
            else 0,
            "overhead_residual_ms_p95": _percentile(overhead_residual_values, 0.95),
            "overhead_residual_ms_p99": _percentile(overhead_residual_values, 0.99),
            "overhead_residual_ms_max": max(overhead_residual_values)
            if overhead_residual_values
            else 0,
            "solve_model_ms_sum": solve_model_sum,
            "solve_model_ms_mean": solve_model_mean,
            "solve_model_ms_p95": _percentile(solve_model_values, 0.95),
            "solve_model_ms_p99": _percentile(solve_model_values, 0.99),
            "solve_model_ms_max": max(solve_model_values) if solve_model_values else 0,
            "solve_bvps_cache_lookup_ms_sum": solve_cache_lookup_sum,
            "solve_bvps_cache_lookup_ms_mean": solve_cache_lookup_mean,
            "solve_bvps_cache_lookup_ms_p95": _percentile(
                solve_cache_lookup_values, 0.95
            ),
            "solve_bvps_cache_lookup_ms_p99": _percentile(
                solve_cache_lookup_values, 0.99
            ),
            "solve_bvps_cache_lookup_ms_max": max(solve_cache_lookup_values)
            if solve_cache_lookup_values
            else 0,
            "solve_other_ms_sum": solve_other_sum,
            "solve_other_ms_mean": solve_other_mean,
            "solve_other_ms_p95": _percentile(solve_other_values, 0.95),
            "solve_other_ms_p99": _percentile(solve_other_values, 0.99),
            "solve_other_ms_max": max(solve_other_values) if solve_other_values else 0,
            "runs_with_costs": len(total_ms_values),
        },
        "runs": results,
    }
    flush_info = store.flush_manifest(force=True)
    if isinstance(flush_info, dict):
        flush_total = _as_int(flush_info.get("total_ms", 0))
        flush_count = _as_int(flush_info.get("flush_count", 0))
        report["metrics"]["suite_store_manifest_flush_ms"] = flush_total
        report["metrics"]["suite_store_manifest_flush_count"] = flush_count
        detail = flush_info.get("detail_ms", {})
        if isinstance(detail, dict):
            for key, value in detail.items():
                value_int = _as_int(value)
                report["metrics"][f"suite_store_manifest_flush_detail_{key}_p95"] = value_int
                report["metrics"][f"suite_store_manifest_flush_detail_{key}_p99"] = value_int
                report["metrics"][f"suite_store_manifest_flush_detail_{key}_max"] = value_int
    persist_stats = bvps_cache.persist_stats_snapshot()
    if persist_stats:
        disable_reason = str(
            persist_stats.get("bvps_persist_disable_reason")
            or persist_stats.get("persist_disable_reason")
            or ""
        )
        suite_meta["bvps_persist_disable_reason"] = disable_reason
        for key, value in persist_stats.items():
            if isinstance(value, (int, float, str, bool)):
                report["metrics"][str(key)] = value
    if suite_meta:
        report["metrics"]["bvps_persist_preload_count"] = _as_int(
            suite_meta.get("bvps_persist_preload_entries")
        )
        report["metrics"]["bvps_persist_preload_errors"] = _as_int(
            suite_meta.get("bvps_persist_preload_errors")
        )
    for key, values in verify_checks_values.items():
        if not values:
            continue
        report["metrics"].update(
            {
                f"verify_checks_{key}_sum": sum(values),
                f"verify_checks_{key}_mean": int(sum(values) / len(values)),
                f"verify_checks_{key}_p95": _percentile(values, 0.95),
                f"verify_checks_{key}_p99": _percentile(values, 0.99),
                f"verify_checks_{key}_max": max(values),
            }
        )
    for key, values in postsolve_detail_values.items():
        if not values:
            continue
        report["metrics"].update(
            {
                f"postsolve_detail_{key}_p95": _percentile(values, 0.95),
                f"postsolve_detail_{key}_p99": _percentile(values, 0.99),
                f"postsolve_detail_{key}_max": max(values),
            }
        )
    for key, values in artifact_plan_detail_values.items():
        if not values:
            continue
        report["metrics"].update(
            {
                f"postsolve_artifact_plan_detail_{key}_p95": _percentile(values, 0.95),
                f"postsolve_artifact_plan_detail_{key}_p99": _percentile(values, 0.99),
                f"postsolve_artifact_plan_detail_{key}_max": max(values),
            }
        )
    for key, values in manifest_detail_values.items():
        if not values:
            continue
        report["metrics"].update(
            {
                f"verify_store_manifest_detail_{key}_p95": _percentile(values, 0.95),
                f"verify_store_manifest_detail_{key}_p99": _percentile(values, 0.99),
                f"verify_store_manifest_detail_{key}_max": max(values),
            }
        )
    report_bytes = canonical_json_bytes(report)
    if out_dir is None:
        out_dir = _default_suite_out_dir(config, suite_spec.suite_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    report_path.write_bytes(report_bytes)
    store.put_bytes(
        report_bytes,
        artifact_type="eval_suite_report",
        media_type="application/json",
        producer="eval",
    )
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
        if isinstance(entry, dict):
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
        elif isinstance(entry, str):
            name = entry
            resolved = _resolve_task_path(entry, path)
        else:
            raise ValueError("suite task entry must be a mapping or string")
        if not resolved.exists():
            raise FileNotFoundError(f"task file not found: {resolved}")
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


def _resolve_task_path(task_value: str, suite_path: Path) -> Path:
    raw = task_value.strip()
    if not raw:
        raise ValueError("suite task entry must be non-empty")
    task_path = Path(raw)
    if task_path.is_absolute():
        return task_path
    if task_path.suffix == ".json" or "/" in raw:
        return (suite_path.parent / task_path).resolve()
    return (Path.cwd() / "examples" / "tasks" / f"{raw}.json").resolve()


def _default_suite_out_dir(config: AppConfig, suite_name: str) -> Path:
    base = config.paths.runs_dir / "suites"
    base.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = _slugify(suite_name)
    stem = f"{timestamp}-{slug}" if slug else timestamp
    candidate = base / stem
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        fallback = base / f"{stem}-r{suffix:02d}"
        if not fallback.exists():
            return fallback
        suffix += 1


def _slugify(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _merge_lane_ms(target: dict[str, int], source: dict[str, Any]) -> None:
    for key, value in source.items():
        normalized = _normalize_lane_name(str(key))
        if not normalized:
            continue
        target[normalized] = target.get(normalized, 0) + _as_int(value)


def _lane_ms_from_verdicts(verdicts: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for lane, verdict in verdicts.items():
        if not isinstance(verdict, dict):
            continue
        name = _normalize_lane_name(lane or verdict.get("lane", ""))
        if not name:
            continue
        totals[name] = totals.get(name, 0) + _as_int(verdict.get("cost_ms"))
    return totals


def _normalize_lane_ms(values: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    _merge_lane_ms(totals, values)
    return totals


def _lane_verdicts_from_list(verdicts: list[Any]) -> dict[str, dict[str, Any]]:
    lane_verdicts: dict[str, dict[str, Any]] = {}
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        lane = str(verdict.get("lane", ""))
        normalized = _normalize_lane_name(lane)
        if not normalized:
            continue
        entry = lane_verdicts.setdefault(
            normalized,
            {
                "status": verdict.get("status"),
                "cost_ms": 0,
                "evidence": [],
                "notes": None,
                "costs": {},
            },
        )
        entry["status"] = verdict.get("status") or entry.get("status")
        entry["cost_ms"] = _as_int(entry.get("cost_ms")) + _as_int(verdict.get("cost_ms"))
        entry["evidence"] = (entry.get("evidence") or []) + (verdict.get("evidence") or [])
        entry["notes"] = verdict.get("notes") or entry.get("notes")
        entry["costs"] = verdict.get("costs", {}) or entry.get("costs", {})
    return lane_verdicts


def _normalize_lane_verdicts(lane_verdicts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for lane, verdict in lane_verdicts.items():
        if not isinstance(verdict, dict):
            continue
        name = _normalize_lane_name(lane or verdict.get("lane", ""))
        if not name:
            continue
        normalized[name] = {
            "status": verdict.get("status"),
            "cost_ms": _as_int(verdict.get("cost_ms")),
            "evidence": verdict.get("evidence", []),
            "notes": verdict.get("notes"),
            "costs": verdict.get("costs", {}),
        }
    return normalized


def _lane_statuses_from_verdicts(lane_verdicts: dict[str, Any]) -> dict[str, Any]:
    return {lane: verdict.get("status") for lane, verdict in lane_verdicts.items()}


def _load_witness_verification(run_dir: Path) -> list[dict[str, Any]]:
    witness_path = run_dir / "witness.json"
    if not witness_path.exists():
        return []
    try:
        payload = json.loads(witness_path.read_text())
    except json.JSONDecodeError:
        return []
    verification = payload.get("verification", [])
    if isinstance(verification, list):
        return [item for item in verification if isinstance(item, dict)]
    return []


def _normalize_lane_name(value: str) -> str:
    name = value.strip().lower()
    for lane in ("recompute", "translation", "consequence", "anchors"):
        if name == lane or name.startswith(f"{lane}_") or name.startswith(f"{lane}-"):
            return lane
    return ""


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    if percentile <= 0:
        return min(values)
    if percentile >= 1:
        return max(values)
    sorted_values = sorted(values)
    idx = int(math.ceil(percentile * len(sorted_values)) - 1)
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_list: list[Any] | None = None
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
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            if item_content and ":" not in item_content:
                if current_item is not None:
                    current_list.append(current_item)
                    current_item = None
                current_list.append(_parse_value(item_content))
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
