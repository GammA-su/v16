from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _pct_change(prev: int, curr: int) -> float:
    if prev <= 0:
        return 0.0 if curr <= prev else 100.0
    return (curr - prev) / prev * 100.0


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default=os.getenv("PERF_HISTORY_PATH", "runs/perf_history.jsonl"),
        help="path to perf_history.jsonl",
    )
    args = parser.parse_args()

    history_path = Path(args.path)
    records = _load_records(history_path)
    if len(records) < 2:
        print(f"perf guard: need at least 2 records in {history_path}")
        return 0

    prev = records[-2]
    curr = records[-1]
    prev_metrics = prev.get("default_metrics", {})
    curr_metrics = curr.get("default_metrics", {})
    if not isinstance(prev_metrics, dict):
        prev_metrics = {}
    if not isinstance(curr_metrics, dict):
        curr_metrics = {}

    thresholds = {
        "total_ms_p95": float(os.getenv("PERF_GUARD_TOTAL_P95_PCT", "10")),
        "total_ms_p99": float(os.getenv("PERF_GUARD_TOTAL_P99_PCT", "15")),
        "verify_phase_ms_p99": float(os.getenv("PERF_GUARD_VERIFY_P99_PCT", "15")),
        "verify_artifact_ms_p95": float(os.getenv("PERF_GUARD_VERIFY_ARTIFACT_P95_PCT", "15")),
        "overhead_ms_p95": float(os.getenv("PERF_GUARD_OVERHEAD_P95_PCT", "20")),
        "overhead_residual_ms_p95": float(
            os.getenv("PERF_GUARD_OVERHEAD_RESIDUAL_P95_PCT", "30")
        ),
    }

    print(f"perf guard history: {history_path}")
    print(f"prev: {prev.get('timestamp')} {prev.get('default_report')}")
    print(f"curr: {curr.get('timestamp')} {curr.get('default_report')}")

    failed = False
    for key, threshold in thresholds.items():
        prev_value = _as_int(prev_metrics.get(key))
        curr_value = _as_int(curr_metrics.get(key))
        delta = curr_value - prev_value
        pct = _pct_change(prev_value, curr_value)
        status = "OK"
        if pct > threshold:
            status = "FAIL"
            failed = True
        print(
            f"{key} prev={prev_value} curr={curr_value} "
            f"delta={delta} pct={pct:.1f}% threshold={threshold:.1f}% {status}"
        )

    if failed:
        print("perf guard FAIL")
        return 1
    print("perf guard PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
