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


def _lane_ms_bits(lane_ms: dict[str, int]) -> str:
    parts = []
    for lane in ("anchors", "consequence", "recompute", "translation"):
        value = lane_ms.get(lane)
        parts.append(f"{lane}:{value if value is not None else '?'}")
    return "lane_ms=" + ",".join(parts)


def _phase_ms_bits(phase_ms: dict[str, Any]) -> str | None:
    if not phase_ms:
        return None
    ordered = ["interpret", "solve", "verify", "decide", "capsule"]
    seen = set()
    parts = []
    for key in ordered:
        if key in phase_ms:
            parts.append(f"{key}:{_as_int(phase_ms.get(key))}")
            seen.add(key)
    for key in sorted(k for k in phase_ms if k not in seen):
        parts.append(f"{key}:{_as_int(phase_ms.get(key))}")
    return "phase_ms=" + ",".join(parts)


def _verify_minus_lane(run: dict[str, Any], lane_ms: dict[str, int]) -> int | None:
    explicit = run.get("verify_minus_lane")
    if explicit is not None:
        return _as_int(explicit)
    phase_ms = run.get("phase_ms")
    if not isinstance(phase_ms, dict):
        return None
    verify_ms = phase_ms.get("verify")
    if verify_ms is None:
        return None
    lane_sum = sum(_as_int(value) for value in lane_ms.values())
    return _as_int(verify_ms) - lane_sum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    report = json.loads(args.report.read_text())
    runs = report.get("runs") or []
    if not isinstance(runs, list):
        runs = []
    rows = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        total_ms = _as_int(run.get("total_ms"))
        lane_ms = _lane_ms_from_run(run)
        phase_ms = run.get("phase_ms")
        if not isinstance(phase_ms, dict):
            phase_ms = {}
        row = {
            "task": run.get("task") or run.get("task_id") or "?",
            "seed": run.get("seed", "?"),
            "run": run.get("episode_id") or run.get("run_dir") or "?",
            "total_ms": total_ms,
            "lane_ms": lane_ms,
            "phase_ms": phase_ms,
            "verify_minus_lane": _verify_minus_lane(run, lane_ms),
        }
        rows.append(row)

    rows.sort(key=lambda item: item["total_ms"], reverse=True)
    for idx, row in enumerate(rows[: max(0, args.top)], start=1):
        bits = [
            f"rank={idx}",
            f"task={row['task']}",
            f"seed={row['seed']}",
            f"run={row['run']}",
            f"total_ms={row['total_ms']}",
            _lane_ms_bits(row["lane_ms"]),
        ]
        phase_bits = _phase_ms_bits(row["phase_ms"])
        if phase_bits:
            bits.append(phase_bits)
        if row["verify_minus_lane"] is not None:
            bits.append(f"verify_minus_lane={row['verify_minus_lane']}")
        print(" ".join(bits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
