from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eidolon_v16.cli_utils import sanitize_ansi_path

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
    parser.add_argument("report", type=str)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    report = json.loads(Path(sanitize_ansi_path(args.report)).read_text())
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
        bvps_cache_state = run.get("bvps_cache")
        if not isinstance(bvps_cache_state, str):
            bvps_cache_state = ""
        bvps_cache_meta = run.get("bvps_cache_meta")
        if not isinstance(bvps_cache_meta, dict):
            bvps_cache_meta = {}
        if not bvps_cache_meta and isinstance(run.get("bvps_cache"), dict):
            bvps_cache_meta = run.get("bvps_cache")
        bvps_ids = run.get("bvps_ids")
        if not isinstance(bvps_ids, dict):
            bvps_ids = {}
        bvps_fastpath = run.get("bvps_fastpath")
        row = {
            "task": run.get("task") or run.get("task_id") or "?",
            "seed": run.get("seed", "?"),
            "run": run.get("episode_id") or run.get("run_dir") or "?",
            "total_ms": total_ms,
            "lane_ms": lane_ms,
            "phase_ms": phase_ms,
            "verify_minus_lane": _verify_minus_lane(run, lane_ms),
            "bvps_cache_state": bvps_cache_state,
            "bvps_cache_meta": bvps_cache_meta,
            "bvps_ids": bvps_ids,
            "bvps_fastpath": bvps_fastpath,
            "spec_hash": run.get("spec_hash"),
            "macros_hash": run.get("macros_hash"),
            "program_hash": run.get("program_hash"),
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
        bvps_cache_state = row.get("bvps_cache_state")
        bvps_cache_meta = row.get("bvps_cache_meta", {})
        cache_label = None
        if isinstance(bvps_cache_state, str) and bvps_cache_state:
            cache_label = bvps_cache_state
        elif isinstance(bvps_cache_meta, dict) and "hit" in bvps_cache_meta:
            hit = "hit" if bvps_cache_meta.get("hit") else "miss"
            scope = str(bvps_cache_meta.get("scope") or "none")
            cache_label = f"{hit}:{scope}"
        if cache_label:
            bits.append(f"bvps_cache={cache_label}")
        spec_hash = row.get("spec_hash") or row.get("bvps_ids", {}).get("spec_hash")
        macros_hash = row.get("macros_hash") or row.get("bvps_ids", {}).get("macros_hash")
        program_hash = row.get("program_hash") or row.get("bvps_ids", {}).get("program_hash")
        if spec_hash:
            bits.append(f"spec_hash={spec_hash}")
        if macros_hash:
            bits.append(f"macros_hash={macros_hash}")
        if program_hash:
            bits.append(f"program_hash={program_hash}")
        if row.get("bvps_fastpath") is not None:
            bits.append(f"bvps_fastpath={bool(row['bvps_fastpath'])}")
        phase_bits = _phase_ms_bits(row["phase_ms"])
        if phase_bits:
            bits.append(phase_bits)
        if row["verify_minus_lane"] is not None:
            bits.append(f"verify_minus_lane={row['verify_minus_lane']}")
        print(" ".join(bits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
