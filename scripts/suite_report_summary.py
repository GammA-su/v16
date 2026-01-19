from __future__ import annotations

import json
import math
import sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/suite_report_summary.py runs/suites/.../report.json")
        return 2
    p = Path(sys.argv[1])
    j = json.loads(p.read_text())

    per = j.get("per_task") or j.get("tasks") or []
    runs = j.get("runs") or []
    bad = []
    if per and isinstance(per[0], str):
        per = []
    if per:
        for t in per:
            status = (t.get("status") or "").upper()
            if status and status != "PASS":
                bad.append(t)
    elif runs:
        for r in runs:
            lane_statuses = r.get("lane_statuses") or {}
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
        print(
            "total_ms sum={} mean={} p95={}".format(
                metrics["total_ms_sum"],
                metrics["total_ms_mean"],
                metrics["total_ms_p95"],
            )
        )
        lane_ms_sum = metrics.get("lane_ms_sum") or {}
        if lane_ms_sum:
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
                "verify_artifact_ms sum={} mean={} p95={}".format(
                    verify_artifact_sum or 0,
                    verify_artifact_mean,
                    verify_artifact_p95,
                )
            )
            print(
                "verify_admission_ms sum={} mean={} p95={}".format(
                    verify_admission_sum or 0,
                    verify_admission_mean,
                    verify_admission_p95,
                )
            )

    for t in bad:
        tid = t.get("task_id") or t.get("task") or t.get("id") or "?"
        status = t.get("status") or "FAIL"
        ep = t.get("episode_id") or t.get("run") or t.get("run_dir") or "?"
        print(f"- {tid} {status} {ep}")

    return 0 if not bad else 1


def _extract_metrics(report: dict[str, object], runs: list[object]) -> dict[str, object] | None:
    metrics = report.get("metrics")
    if isinstance(metrics, dict) and metrics.get("total_ms_sum") is not None:
        return metrics
    total_ms_values: list[int] = []
    lane_ms_sum: dict[str, int] = {}
    verify_artifact_values: list[int] = []
    verify_admission_values: list[int] = []
    for item in runs:
        if not isinstance(item, dict):
            continue
        total_ms = _as_int(item.get("total_ms"))
        if total_ms:
            total_ms_values.append(total_ms)
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
    if not total_ms_values and not lane_ms_sum:
        return None
    total_ms_sum = sum(total_ms_values)
    total_ms_mean = int(total_ms_sum / len(total_ms_values)) if total_ms_values else 0
    total_ms_p95 = _percentile(total_ms_values, 0.95)
    metrics: dict[str, object] = {
        "total_ms_sum": total_ms_sum,
        "total_ms_mean": total_ms_mean,
        "total_ms_p95": total_ms_p95,
        "lane_ms_sum": lane_ms_sum,
    }
    if verify_artifact_values:
        metrics.update(
            {
                "verify_artifact_ms_sum": sum(verify_artifact_values),
                "verify_artifact_ms_mean": int(
                    sum(verify_artifact_values) / len(verify_artifact_values)
                ),
                "verify_artifact_ms_p95": _percentile(verify_artifact_values, 0.95),
            }
        )
    if verify_admission_values:
        metrics.update(
            {
                "verify_admission_ms_sum": sum(verify_admission_values),
                "verify_admission_ms_mean": int(
                    sum(verify_admission_values) / len(verify_admission_values)
                ),
                "verify_admission_ms_p95": _percentile(verify_admission_values, 0.95),
            }
        )
    return metrics


def _as_int(value: object) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _merge_lane_ms(target: dict[str, int], source: dict[str, object]) -> None:
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


def _lane_ms_from_run(run: dict[str, object]) -> dict[str, int] | None:
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
