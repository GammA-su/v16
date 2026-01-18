from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LANES = ("recompute", "translation", "consequence", "anchors")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _normalize_lane(name: Any) -> str:
    value = str(name).strip().lower()
    return value if value in LANES else ""


def _lane_ms_from_verdicts(verdicts: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for lane, verdict in verdicts.items():
        if not isinstance(verdict, dict):
            continue
        normalized = _normalize_lane(lane or verdict.get("lane", ""))
        if not normalized:
            continue
        totals[normalized] = totals.get(normalized, 0) + _as_int(verdict.get("cost_ms"))
    return totals


def _lane_ms_from_run(run: dict[str, Any]) -> dict[str, int]:
    lane_ms = run.get("lane_ms")
    if isinstance(lane_ms, dict):
        totals: dict[str, int] = {}
        for lane, value in lane_ms.items():
            normalized = _normalize_lane(lane)
            if not normalized:
                continue
            totals[normalized] = totals.get(normalized, 0) + _as_int(value)
        return totals
    verdicts = run.get("lane_verdicts")
    if isinstance(verdicts, dict):
        return _lane_ms_from_verdicts(verdicts)
    return {}


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    values = sorted(values)
    idx = int((len(values) - 1) * 0.95)
    return values[idx]


def _summarize(report: dict[str, Any]) -> dict[str, Any]:
    runs = report.get("runs") or []
    total_ms_values: list[int] = []
    lane_ms_sum: dict[str, int] = {lane: 0 for lane in LANES}
    lane_ms_counts: dict[str, int] = {lane: 0 for lane in LANES}
    failing = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        if _is_failing(run):
            failing += 1
        total_ms_value = run.get("total_ms")
        if total_ms_value is not None:
            total_ms = _as_int(total_ms_value)
            total_ms_values.append(total_ms)
        lane_ms = _lane_ms_from_run(run)
        for lane in LANES:
            if lane not in lane_ms:
                continue
            lane_ms_sum[lane] = lane_ms_sum.get(lane, 0) + _as_int(lane_ms.get(lane))
            lane_ms_counts[lane] = lane_ms_counts.get(lane, 0) + 1
    total_ms_sum = sum(total_ms_values)
    total_ms_mean = int(total_ms_sum / len(total_ms_values)) if total_ms_values else 0
    return {
        "failing": failing,
        "total_ms_sum": total_ms_sum,
        "total_ms_mean": total_ms_mean,
        "total_ms_p95": _p95(total_ms_values),
        "lane_ms_sum": lane_ms_sum,
        "lane_ms_mean": {
            lane: (
                int(lane_ms_sum.get(lane, 0) / lane_ms_counts.get(lane, 0))
                if lane_ms_counts.get(lane, 0)
                else 0
            )
            for lane in LANES
        },
    }


def _is_failing(run: dict[str, Any]) -> bool:
    status = run.get("status")
    if status is not None:
        return str(status).upper() != "PASS"
    lane_statuses = run.get("lane_statuses") or {}
    if not lane_statuses:
        return True
    return any(str(status).upper() != "PASS" for status in lane_statuses.values())


def _fmt(label: str, summary: dict[str, Any]) -> None:
    print(f"{label}: failing={summary['failing']}")
    print(
        "  total_ms sum={} mean={} p95={}".format(
            summary["total_ms_sum"],
            summary["total_ms_mean"],
            summary["total_ms_p95"],
        )
    )
    lane_sum = summary.get("lane_ms_sum", {})
    lane_mean = summary.get("lane_ms_mean", {})
    lane_sum_bits = " ".join(f"{k}={lane_sum.get(k, 0)}" for k in LANES)
    lane_mean_bits = " ".join(f"{k}={lane_mean.get(k, 0)}" for k in LANES)
    print(f"  lane_ms sum {lane_sum_bits}")
    print(f"  lane_ms mean {lane_mean_bits}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sk_report", type=Path)
    parser.add_argument("ns_report", type=Path)
    args = parser.parse_args()

    sk = _summarize(_load(args.sk_report))
    ns = _summarize(_load(args.ns_report))

    _fmt("SK", sk)
    _fmt("NS", ns)

    print("Delta (SK - NS):")
    print(
        "  total_ms sum={} mean={} p95={}".format(
            sk["total_ms_sum"] - ns["total_ms_sum"],
            sk["total_ms_mean"] - ns["total_ms_mean"],
            sk["total_ms_p95"] - ns["total_ms_p95"],
        )
    )
    lane_sum_delta = " ".join(
        f"{lane}={sk['lane_ms_sum'].get(lane, 0) - ns['lane_ms_sum'].get(lane, 0)}"
        for lane in LANES
    )
    lane_mean_delta = " ".join(
        f"{lane}={sk['lane_ms_mean'].get(lane, 0) - ns['lane_ms_mean'].get(lane, 0)}"
        for lane in LANES
    )
    print(f"  lane_ms sum {lane_sum_delta}")
    print(f"  lane_ms mean {lane_mean_delta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
