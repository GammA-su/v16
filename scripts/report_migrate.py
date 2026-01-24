from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any


def _expand_inputs(items: list[object]) -> list[Path]:
    resolved: list[Path] = []
    seen: set[str] = set()
    missing: list[str] = []
    for item in items:
        item_str = str(item)
        matches = sorted(glob(item_str))
        if matches:
            for match in matches:
                path = Path(match)
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                resolved.append(path)
        else:
            path = Path(item_str)
            if path.exists():
                key = str(path)
                if key not in seen:
                    seen.add(key)
                    resolved.append(path)
            else:
                missing.append(item_str)
    if missing:
        print(f"missing inputs: {', '.join(missing)}")
        raise SystemExit(2)
    if not resolved:
        print("no inputs matched")
        raise SystemExit(2)
    return resolved


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _ensure_report_meta(report: dict[str, Any]) -> dict[str, Any]:
    meta = report.get("report_meta")
    if not isinstance(meta, dict):
        meta = {}
    def _non_empty(value: object) -> bool:
        return isinstance(value, str) and value.strip() != ""

    if not _non_empty(meta.get("created_utc")):
        meta["created_utc"] = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if not _non_empty(meta.get("git_sha")):
        meta["git_sha"] = "unknown"
    if not _non_empty(str(meta.get("git_dirty", ""))):
        meta["git_dirty"] = "unknown"
    if not _non_empty(meta.get("host")):
        meta["host"] = socket.gethostname() or "unknown"
    pid = meta.get("pid")
    if pid is None or str(pid).strip() == "":
        meta["pid"] = os.getpid()
    if not _non_empty(meta.get("python")):
        meta["python"] = sys.version.split()[0] if sys.version else "unknown"
    config_flags = meta.get("config_flags")
    if not isinstance(config_flags, dict):
        meta["config_flags"] = {}
    report["report_meta"] = meta
    return meta


def _extract_runs(report: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("runs", "results", "items"):
        runs = report.get(key)
        if isinstance(runs, list):
            return [run for run in runs if isinstance(run, dict)]
    return []


def _has_ms(run: dict[str, Any], check_name: str) -> bool:
    key = f"verify_check_{check_name}_ms"
    metrics = run.get("metrics")
    if isinstance(metrics, dict) and _is_number(metrics.get(key)):
        return True
    checks = run.get("verify_checks_ms")
    if isinstance(checks, dict):
        if f"{check_name}_ms" in checks:
            return True
    value = run.get(key)
    if _is_number(value) and float(value) > 0:
        return True
    return False


def migrate_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = dict(payload)
    _ensure_report_meta(report)
    runs = _extract_runs(report)
    count_keys = (
        "verify_domain",
        "verify_format",
        "verify_task_verifier",
    )
    for run in runs:
        for check in count_keys:
            count_key = f"verify_check_{check}_count"
            count_value = 1 if _has_ms(run, check) else 0
            run[count_key] = count_value
        checks = run.get("verify_checks_ms")
        if not isinstance(checks, dict):
            checks = {}
        run.setdefault(
            "verify_check_verify_domain_ms",
            int(checks.get("verify_domain_ms", 0) or 0),
        )
        run.setdefault(
            "verify_check_verify_format_ms",
            int(checks.get("verify_format_ms", 0) or 0),
        )
        run.setdefault(
            "verify_check_verify_task_verifier_ms",
            int(checks.get("verify_task_verifier_ms", 0) or 0),
        )
        for field in (
            "overhead_breakdown_ms",
            "verify_breakdown_ms",
            "verify_task_verifier_detail_ms",
            "solve_breakdown_ms",
            "phase_ms",
        ):
            nested = run.get(field)
            if isinstance(nested, dict):
                prefix = "verify_task_verifier_detail" if field == "verify_task_verifier_detail_ms" else ""
                for key, value in _flatten_ms(prefix, nested).items():
                    run.setdefault(key, value)
        postsolve_misc_detail = run.get("postsolve_misc_detail_ms")
        if isinstance(postsolve_misc_detail, dict):
            for key, value in _flatten_ms("postsolve_misc_detail", postsolve_misc_detail).items():
                run.setdefault(key, value)
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    for check in count_keys:
        metric_key = f"verify_checks_{check}_count"
        if metric_key in metrics:
            continue
        metrics[metric_key] = sum(
            1 for run in runs if _has_ms(run, check)
        )
    report["metrics"] = metrics
    return report


def _dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _flatten_ms(prefix: str, obj: dict[str, Any]) -> dict[str, int | float]:
    flattened: dict[str, int | float] = {}
    for key, value in obj.items():
        key_str = str(key)
        if isinstance(value, dict) and key_str.endswith("_ms"):
            key_str = key_str[:-3]
        next_prefix = f"{prefix}_{key_str}" if prefix else key_str
        if isinstance(value, dict):
            flattened.update(_flatten_ms(next_prefix, value))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            flattened[next_prefix] = value
    return flattened


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate report.json to add meta/counts.")
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()

    paths = _expand_inputs(args.reports)
    for path in paths:
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            payload = {}
        migrated = migrate_report(payload)
        if args.in_place:
            path.write_text(_dump_json(migrated))
        else:
            print(_dump_json(migrated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
