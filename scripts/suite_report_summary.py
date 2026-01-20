from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from eidolon_v16.cli_utils import sanitize_ansi_path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/suite_report_summary.py runs/suites/.../report.json")
        return 2
    p = Path(sanitize_ansi_path(sys.argv[1]))
    j = _load_report(p)

    per_raw = j.get("per_task") or j.get("tasks") or []
    runs_raw = j.get("runs") or []
    per: list[object] = per_raw if isinstance(per_raw, list) else []
    runs: list[object] = runs_raw if isinstance(runs_raw, list) else []
    bad: list[dict[str, Any]] = []
    if per and isinstance(per[0], str):
        per = []
    if per:
        for t in per:
            if not isinstance(t, dict):
                continue
            status = (t.get("status") or "").upper()
            if status and status != "PASS":
                bad.append(t)
    elif runs:
        for r in runs:
            if not isinstance(r, dict):
                continue
            lane_statuses = r.get("lane_statuses") or {}
            if not isinstance(lane_statuses, dict):
                lane_statuses = {}
            status = "PASS" if lane_statuses and all(
                (str(v).upper() == "PASS") for v in lane_statuses.values()
            ) else "FAIL"
            if status != "PASS":
                bad.append(r)

    print(f"report: {p}")
    total = len(per) if per else len(runs)
    print(f"tasks: {total}  failing: {len(bad)}")

    metrics = _extract_metrics(j, runs)
    if metrics is not None:
        total_ms_sum = metrics.get("total_ms_sum", 0)
        total_ms_mean = metrics.get("total_ms_mean", 0)
        total_ms_p95 = metrics.get("total_ms_p95", 0)
        total_ms_p99 = metrics.get("total_ms_p99", 0)
        total_ms_max = metrics.get("total_ms_max", 0)
        print(
            f"total_ms sum={total_ms_sum} "
            f"mean={total_ms_mean} "
            f"p95={total_ms_p95} "
            f"p99={total_ms_p99} "
            f"max={total_ms_max}"
        )
    verify_phase_p99 = metrics.get("verify_phase_ms_p99")
    verify_phase_max = metrics.get("verify_phase_ms_max")
    if verify_phase_p99 is not None or verify_phase_max is not None:
        print(
            "verify_phase_ms "
            f"p99={verify_phase_p99 or 0} "
            f"max={verify_phase_max or 0}"
        )
        lane_ms_sum = metrics.get("lane_ms_sum")
        if isinstance(lane_ms_sum, dict) and lane_ms_sum:
            lane_bits = " ".join(f"{k}={v}" for k, v in sorted(lane_ms_sum.items()))
            print(f"lane_ms sum {lane_bits}")
        verify_artifact_sum = metrics.get("verify_artifact_ms_sum")
        verify_admission_sum = metrics.get("verify_admission_ms_sum")
        if verify_artifact_sum is not None or verify_admission_sum is not None:
            verify_artifact_mean = metrics.get("verify_artifact_ms_mean", 0)
            verify_artifact_p95 = metrics.get("verify_artifact_ms_p95", 0)
            verify_admission_mean = metrics.get("verify_admission_ms_mean", 0)
            verify_admission_p95 = metrics.get("verify_admission_ms_p95", 0)
            print(
                f"verify_artifact_ms sum={verify_artifact_sum or 0} "
                f"mean={verify_artifact_mean} "
                f"p95={verify_artifact_p95}"
            )
            print(
                f"verify_admission_ms sum={verify_admission_sum or 0} "
                f"mean={verify_admission_mean} "
                f"p95={verify_admission_p95}"
            )
        run_dir_sum = metrics.get("verify_run_dir_write_ms_sum")
        json_sum = metrics.get("verify_json_serialize_ms_sum")
        if run_dir_sum is not None:
            print(
                "verify_run_dir_write_ms sum="
                f"{run_dir_sum or 0} mean={metrics.get('verify_run_dir_write_ms_mean', 0)} "
                f"p95={metrics.get('verify_run_dir_write_ms_p95', 0)} "
                f"p99={metrics.get('verify_run_dir_write_ms_p99', 0)} "
                f"max={metrics.get('verify_run_dir_write_ms_max', 0)}"
            )
        if json_sum is not None:
            print(
                "verify_json_serialize_ms sum="
                f"{json_sum or 0} mean={metrics.get('verify_json_serialize_ms_mean', 0)} "
                f"p95={metrics.get('verify_json_serialize_ms_p95', 0)} "
                f"p99={metrics.get('verify_json_serialize_ms_p99', 0)} "
                f"max={metrics.get('verify_json_serialize_ms_max', 0)}"
            )
        store_keys = sorted(
            key[len("verify_store_") : -len("_sum")]
            for key in metrics
            if key.startswith("verify_store_") and key.endswith("_sum")
        )
        for key in store_keys:
            store_sum = metrics.get(f"verify_store_{key}_sum", 0)
            store_mean = metrics.get(f"verify_store_{key}_mean", 0)
            store_p95 = metrics.get(f"verify_store_{key}_p95", 0)
            print(
                f"verify_store_{key} sum={store_sum} "
                f"mean={store_mean} "
                f"p95={store_p95}"
            )
        solve_keys = sorted(
            key[len("solve_bvps_") : -len("_sum")]
            for key in metrics
            if key.startswith("solve_bvps_") and key.endswith("_sum")
        )
        for key in solve_keys:
            solve_sum = metrics.get(f"solve_bvps_{key}_sum", 0)
            solve_mean = metrics.get(f"solve_bvps_{key}_mean", 0)
            solve_p95 = metrics.get(f"solve_bvps_{key}_p95", 0)
            print(
                f"solve_bvps_{key} sum={solve_sum} "
                f"mean={solve_mean} "
                f"p95={solve_p95}"
            )
        hits_mem = metrics.get("bvps_cache_hits_mem")
        hits_persist = metrics.get("bvps_cache_hits_persist")
        misses = metrics.get("bvps_cache_misses")
        if hits_mem is not None or hits_persist is not None or misses is not None:
            print(
                "bvps_cache hits_mem="
                f"{hits_mem or 0} hits_persist={hits_persist or 0} "
                f"misses={misses or 0}"
            )

    for t in bad:
        tid = t.get("task_id") or t.get("task") or t.get("id") or "?"
        status = t.get("status") or "FAIL"
        ep = t.get("episode_id") or t.get("run") or t.get("run_dir") or "?"
        print(f"- {tid} {status} {ep}")

    return 0 if not bad else 1


def _load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return {}


def _extract_metrics(report: dict[str, Any], runs: list[object]) -> dict[str, Any] | None:
    existing = report.get("metrics")
    total_ms_values: list[int] = []
    lane_ms_sum: dict[str, int] = {}
    verify_artifact_values: list[int] = []
    verify_admission_values: list[int] = []
    verify_run_dir_write_values: list[int] = []
    verify_json_serialize_values: list[int] = []
    verify_phase_values: list[int] = []
    verify_store_values: dict[str, list[int]] = {}
    solve_breakdown_values: dict[str, list[int]] = {}
    bvps_cache_hits_mem = 0
    bvps_cache_hits_persist = 0
    bvps_cache_misses = 0
    bvps_cache_seen = False
    for item in runs:
        if not isinstance(item, dict):
            continue
        total_ms = _as_int(item.get("total_ms"))
        if total_ms:
            total_ms_values.append(total_ms)
        phase_ms = item.get("phase_ms")
        if isinstance(phase_ms, dict) and "verify" in phase_ms:
            verify_phase_values.append(_as_int(phase_ms.get("verify")))
        lane_ms = _lane_ms_from_run(item)
        if lane_ms is not None:
            _merge_lane_ms(lane_ms_sum, lane_ms)
        verify_breakdown = item.get("verify_breakdown_ms")
        if isinstance(verify_breakdown, dict):
            if "verify_artifact_ms" in verify_breakdown:
                verify_artifact_values.append(_as_int(verify_breakdown.get("verify_artifact_ms")))
            if "verify_admission_ms" in verify_breakdown:
                verify_admission_values.append(
                    _as_int(verify_breakdown.get("verify_admission_ms"))
                )
            if "verify_run_dir_write_ms" in verify_breakdown:
                verify_run_dir_write_values.append(
                    _as_int(verify_breakdown.get("verify_run_dir_write_ms"))
                )
            if "verify_json_serialize_ms" in verify_breakdown:
                verify_json_serialize_values.append(
                    _as_int(verify_breakdown.get("verify_json_serialize_ms"))
                )
            store_breakdown = verify_breakdown.get("verify_store_ms")
            if isinstance(store_breakdown, dict):
                for key, value in store_breakdown.items():
                    verify_store_values.setdefault(str(key), []).append(_as_int(value))
        solve_breakdown = item.get("solve_breakdown_ms")
        if isinstance(solve_breakdown, dict):
            for key, value in solve_breakdown.items():
                solve_breakdown_values.setdefault(str(key), []).append(_as_int(value))
        bvps_cache = item.get("bvps_cache")
        cache_state = ""
        if isinstance(bvps_cache, str):
            cache_state = bvps_cache
        elif isinstance(bvps_cache, dict) and "hit" in bvps_cache:
            hit = "hit" if bvps_cache.get("hit") else "miss"
            scope = str(bvps_cache.get("scope") or "none")
            cache_state = f"{hit}:{scope}"
        if cache_state:
            bvps_cache_seen = True
            if cache_state == "hit:mem":
                bvps_cache_hits_mem += 1
            elif cache_state == "hit:persist":
                bvps_cache_hits_persist += 1
            else:
                bvps_cache_misses += 1
    if not total_ms_values and not lane_ms_sum:
        if isinstance(existing, dict) and existing.get("total_ms_sum") is not None:
            return cast(dict[str, Any], existing)
        return None
    total_ms_sum = sum(total_ms_values)
    total_ms_mean = int(total_ms_sum / len(total_ms_values)) if total_ms_values else 0
    total_ms_p95 = _percentile(total_ms_values, 0.95)
    total_ms_p99 = _percentile(total_ms_values, 0.99)
    total_ms_max = max(total_ms_values) if total_ms_values else 0
    computed: dict[str, Any] = {
        "total_ms_sum": total_ms_sum,
        "total_ms_mean": total_ms_mean,
        "total_ms_p95": total_ms_p95,
        "total_ms_p99": total_ms_p99,
        "total_ms_max": total_ms_max,
        "lane_ms_sum": lane_ms_sum,
    }
    if verify_artifact_values:
        computed.update(
            {
                "verify_artifact_ms_sum": sum(verify_artifact_values),
                "verify_artifact_ms_mean": int(
                    sum(verify_artifact_values) / len(verify_artifact_values)
                ),
                "verify_artifact_ms_p95": _percentile(verify_artifact_values, 0.95),
            }
        )
    if verify_admission_values:
        computed.update(
            {
                "verify_admission_ms_sum": sum(verify_admission_values),
                "verify_admission_ms_mean": int(
                    sum(verify_admission_values) / len(verify_admission_values)
                ),
                "verify_admission_ms_p95": _percentile(verify_admission_values, 0.95),
            }
        )
    if verify_run_dir_write_values:
        computed.update(
            {
                "verify_run_dir_write_ms_sum": sum(verify_run_dir_write_values),
                "verify_run_dir_write_ms_mean": int(
                    sum(verify_run_dir_write_values) / len(verify_run_dir_write_values)
                ),
                "verify_run_dir_write_ms_p95": _percentile(
                    verify_run_dir_write_values, 0.95
                ),
                "verify_run_dir_write_ms_p99": _percentile(
                    verify_run_dir_write_values, 0.99
                ),
                "verify_run_dir_write_ms_max": max(verify_run_dir_write_values),
            }
        )
    if verify_json_serialize_values:
        computed.update(
            {
                "verify_json_serialize_ms_sum": sum(verify_json_serialize_values),
                "verify_json_serialize_ms_mean": int(
                    sum(verify_json_serialize_values) / len(verify_json_serialize_values)
                ),
                "verify_json_serialize_ms_p95": _percentile(
                    verify_json_serialize_values, 0.95
                ),
                "verify_json_serialize_ms_p99": _percentile(
                    verify_json_serialize_values, 0.99
                ),
                "verify_json_serialize_ms_max": max(verify_json_serialize_values),
            }
        )
    for key, values in verify_store_values.items():
        if not values:
            continue
        computed.update(
            {
                f"verify_store_{key}_sum": sum(values),
                f"verify_store_{key}_mean": int(sum(values) / len(values)),
                f"verify_store_{key}_p95": _percentile(values, 0.95),
            }
        )
    for key, values in solve_breakdown_values.items():
        if not values:
            continue
        computed.update(
            {
                f"solve_bvps_{key}_sum": sum(values),
                f"solve_bvps_{key}_mean": int(sum(values) / len(values)),
                f"solve_bvps_{key}_p95": _percentile(values, 0.95),
            }
        )
    if bvps_cache_seen:
        computed["bvps_cache_hits_mem"] = bvps_cache_hits_mem
        computed["bvps_cache_hits_persist"] = bvps_cache_hits_persist
        computed["bvps_cache_misses"] = bvps_cache_misses
    if verify_phase_values:
        computed["verify_phase_ms_p99"] = _percentile(verify_phase_values, 0.99)
        computed["verify_phase_ms_max"] = max(verify_phase_values)
    if isinstance(existing, dict) and existing.get("total_ms_sum") is not None:
        for key, value in existing.items():
            computed.setdefault(key, value)
    return computed


def _as_int(value: object) -> int:
    try:
        return int(cast(Any, value)) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _merge_lane_ms(target: dict[str, int], source: Mapping[str, object]) -> None:
    for key, value in source.items():
        lane = _normalize_lane_name(str(key))
        if not lane:
            continue
        target[lane] = target.get(lane, 0) + _as_int(value)


def _lane_ms_from_verdicts(lane_verdicts: object) -> dict[str, int]:
    totals: dict[str, int] = {}
    items: list[tuple[str | None, object]] = []
    if isinstance(lane_verdicts, dict):
        items = [(lane, verdict) for lane, verdict in lane_verdicts.items()]
    elif isinstance(lane_verdicts, list):
        items = [(None, verdict) for verdict in lane_verdicts]
    for lane, verdict in items:
        if not isinstance(verdict, dict):
            continue
        name = _normalize_lane_name(str(lane or verdict.get("lane", "")))
        if not name:
            continue
        totals[name] = totals.get(name, 0) + _as_int(verdict.get("cost_ms"))
    return totals


def _lane_ms_from_run(run: dict[str, Any]) -> dict[str, int] | None:
    lane_ms = run.get("lane_ms")
    if isinstance(lane_ms, dict):
        totals: dict[str, int] = {}
        _merge_lane_ms(totals, lane_ms)
        return totals
    lane_verdicts = run.get("lane_verdicts")
    if isinstance(lane_verdicts, (dict, list)):
        return _lane_ms_from_verdicts(lane_verdicts)
    return {}


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


if __name__ == "__main__":
    raise SystemExit(main())
