from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LANES = ("recompute", "translation", "consequence", "anchors")


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_lane(name: Any) -> str:
    value = str(name).strip().lower()
    for lane in LANES:
        if value == lane or value.startswith(f"{lane}_") or value.startswith(f"{lane}-"):
            return lane
    return ""


def _lane_ms_from_verdicts(verdicts: Any) -> dict[str, int]:
    totals: dict[str, int] = {}
    items: list[tuple[str | None, Any]] = []
    if isinstance(verdicts, dict):
        items = [(lane, verdict) for lane, verdict in verdicts.items()]
    elif isinstance(verdicts, list):
        items = [(None, verdict) for verdict in verdicts]
    for lane, verdict in items:
        if not isinstance(verdict, dict):
            continue
        normalized = _normalize_lane(lane or verdict.get("lane", ""))
        if not normalized:
            continue
        totals[normalized] = totals.get(normalized, 0) + _as_int(verdict.get("cost_ms"))
    return totals


def _lane_ms_from_run(run: dict[str, Any]) -> dict[str, int]:
    lane_ms = run.get("lane_ms")
    if isinstance(lane_ms, dict) and lane_ms:
        totals: dict[str, int] = {}
        for lane, value in lane_ms.items():
            normalized = _normalize_lane(lane)
            if not normalized:
                continue
            totals[normalized] = totals.get(normalized, 0) + _as_int(value)
        return totals
    verdicts = run.get("lane_verdicts")
    if isinstance(verdicts, (dict, list)):
        return _lane_ms_from_verdicts(verdicts)
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    report = json.loads(args.report.read_text())
    runs = report.get("runs") or []
    rows = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        total_ms = _as_int(run.get("total_ms"))
        lane_ms = _lane_ms_from_run(run)
        row = {
            "task": run.get("task") or run.get("task_id") or "?",
            "seed": run.get("seed", "?"),
            "run": run.get("episode_id") or run.get("run_dir") or "?",
            "total_ms": total_ms,
            "lane_ms": lane_ms,
        }
        rows.append(row)

    rows.sort(key=lambda item: item["total_ms"], reverse=True)
    for row in rows[: max(0, args.top)]:
        lane_bits = " ".join(f"{lane}={row['lane_ms'].get(lane, 0)}" for lane in LANES)
        print(
            "task={} seed={} run={} total_ms={} {}".format(
                row["task"],
                row["seed"],
                row["run"],
                row["total_ms"],
                lane_bits,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
