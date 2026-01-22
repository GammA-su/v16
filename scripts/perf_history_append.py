from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidolon_v16.cli_utils import sanitize_ansi_path


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _flush_detail(metrics: dict[str, Any]) -> dict[str, int]:
    detail: dict[str, int] = {}
    for key, value in metrics.items():
        if not key.startswith("suite_store_manifest_flush_detail_") or not key.endswith(
            "_p95"
        ):
            continue
        name = key[len("suite_store_manifest_flush_detail_") : -len("_p95")]
        detail[name] = _as_int(value)
    return detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=str)
    parser.add_argument(
        "--out",
        type=str,
        default="runs/perf_history.jsonl",
        help="Path to perf history jsonl file.",
    )
    args = parser.parse_args()

    report_path = Path(sanitize_ansi_path(args.report))
    payload = json.loads(report_path.read_text())
    if not isinstance(payload, dict):
        raise SystemExit("invalid report payload")
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    suite_meta = payload.get("suite_meta", {})
    if not isinstance(suite_meta, dict):
        suite_meta = {}

    record = {
        "git_sha": _git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite_name": str(payload.get("suite_name") or ""),
        "preload_enabled": bool(_as_int(suite_meta.get("bvps_persist_preload_ms"))),
        "total_ms_mean": _as_int(metrics.get("total_ms_mean")),
        "total_ms_p95": _as_int(metrics.get("total_ms_p95")),
        "total_ms_p99": _as_int(metrics.get("total_ms_p99")),
        "overhead_ms_p95": _as_int(metrics.get("overhead_ms_p95")),
        "suite_store_manifest_flush_ms": _as_int(
            metrics.get("suite_store_manifest_flush_ms")
        ),
        "suite_store_manifest_flush_detail_ms": _flush_detail(metrics),
        "postsolve_artifact_plan_ms_p95": _as_int(
            metrics.get("postsolve_detail_postsolve_artifact_plan_ms_p95")
        ),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
