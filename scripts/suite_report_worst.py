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


def _solve_breakdown_bits(solve_breakdown: dict[str, Any]) -> str | None:
    if not solve_breakdown:
        return None
    fields = (
        "solve_task_load_ms",
        "solve_model_ms",
        "solve_bvps_cache_lookup_ms",
        "solve_bvps_fastpath_ms",
        "solve_other_ms",
    )
    parts = []
    for key in fields:
        if key not in solve_breakdown:
            continue
        label = key.replace("solve_", "").replace("_ms", "")
        parts.append(f"{label}:{_as_int(solve_breakdown.get(key))}")
    if not parts:
        return None
    return "solve_ms=" + ",".join(parts)


def _largest_verify_check(verify_checks: dict[str, Any]) -> tuple[str, int] | None:
    best_key = ""
    best_value = 0
    for key, value in verify_checks.items():
        value_int = _as_int(value)
        if value_int > best_value:
            best_key = str(key)
            best_value = value_int
    if not best_key:
        return None
    return best_key, best_value


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
    parser.add_argument("--sort", type=str, choices=("total", "overhead"), default="total")
    args = parser.parse_args()

    report = json.loads(Path(sanitize_ansi_path(args.report)).read_text())
    metrics = report.get("metrics")
    if args.sort == "overhead" and isinstance(metrics, dict):
        mode = metrics.get("store_manifest_flush_mode")
        count = metrics.get("suite_store_manifest_flush_count")
        flush_ms = metrics.get("suite_store_manifest_flush_ms")
        if mode is not None or count is not None or flush_ms is not None:
            print(f"manifest_flush mode={mode} count={count} ms={flush_ms}")
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
        solve_breakdown = run.get("solve_breakdown_ms")
        if not isinstance(solve_breakdown, dict):
            solve_breakdown = {}
        verify_checks = run.get("verify_checks_ms")
        if not isinstance(verify_checks, dict):
            verify_checks = {}
        overhead_breakdown = run.get("overhead_breakdown_ms")
        if not isinstance(overhead_breakdown, dict):
            overhead_breakdown = {}
        row = {
            "task": run.get("task") or run.get("task_id") or "?",
            "seed": run.get("seed", "?"),
            "run": run.get("episode_id") or run.get("run_dir") or "?",
            "total_ms": total_ms,
            "overhead_ms": _as_int(run.get("overhead_ms")),
            "lane_ms": lane_ms,
            "phase_ms": phase_ms,
            "verify_minus_lane": _verify_minus_lane(run, lane_ms),
            "verify_checks": verify_checks,
            "overhead_breakdown": overhead_breakdown,
            "bvps_cache_state": bvps_cache_state,
            "bvps_cache_meta": bvps_cache_meta,
            "bvps_ids": bvps_ids,
            "bvps_fastpath": bvps_fastpath,
            "solve_breakdown": solve_breakdown,
            "spec_hash": run.get("spec_hash"),
            "macros_hash": run.get("macros_hash"),
            "program_hash": run.get("program_hash"),
        }
        rows.append(row)

    if args.sort == "overhead":
        rows.sort(key=lambda item: item["overhead_ms"], reverse=True)
    else:
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
        solve_bits = _solve_breakdown_bits(row.get("solve_breakdown", {}))
        if solve_bits:
            bits.append(solve_bits)
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
        overhead_ms = row.get("overhead_ms", 0)
        bits.append(f"overhead_ms={overhead_ms}")
        if (
            isinstance(overhead_ms, int)
            and row.get("total_ms")
            and overhead_ms >= int(row["total_ms"] * 0.6)
        ):
            bits.append("gap_monster")
        overhead_breakdown = row.get("overhead_breakdown", {})
        if isinstance(overhead_breakdown, dict) and overhead_breakdown:
            startup = _as_int(overhead_breakdown.get("overhead_startup_ms"))
            postsolve = _as_int(overhead_breakdown.get("overhead_postsolve_ms"))
            postverify = _as_int(overhead_breakdown.get("overhead_postverify_ms"))
            postcapsule = _as_int(overhead_breakdown.get("overhead_postcapsule_ms"))
            residual = _as_int(overhead_breakdown.get("overhead_residual_ms"))
            bits.append(
                "overhead="
                f"startup:{startup} "
                f"postsolve:{postsolve} "
                f"postverify:{postverify} "
                f"postcapsule:{postcapsule} "
                f"residual:{residual}"
            )
            if args.sort == "overhead":
                postsolve_detail = overhead_breakdown.get("postsolve_detail_ms")
                if isinstance(postsolve_detail, dict) and postsolve_detail:
                    detail_bits = " ".join(
                        f"{key}:{_as_int(value)}"
                        for key, value in sorted(postsolve_detail.items())
                    )
                    bits.append(f"postsolve_detail={detail_bits}")
                artifact_plan_detail = overhead_breakdown.get(
                    "postsolve_artifact_plan_detail_ms"
                )
                if isinstance(artifact_plan_detail, dict) and artifact_plan_detail:
                    detail_bits = " ".join(
                        f"{key}:{_as_int(value)}"
                        for key, value in sorted(artifact_plan_detail.items())
                    )
                    bits.append(f"artifact_plan_detail={detail_bits}")
                manifest_detail = overhead_breakdown.get("verify_store_manifest_detail_ms")
                if isinstance(manifest_detail, dict) and manifest_detail:
                    detail_bits = " ".join(
                        f"{key}:{_as_int(value)}"
                        for key, value in sorted(manifest_detail.items())
                    )
                    bits.append(f"manifest_detail={detail_bits}")
        verify_check = _largest_verify_check(row.get("verify_checks", {}))
        if verify_check is not None:
            bits.append(f"verify_check={verify_check[0]}:{verify_check[1]}")
        if row["verify_minus_lane"] is not None:
            bits.append(f"verify_minus_lane={row['verify_minus_lane']}")
        print(" ".join(bits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
