from __future__ import annotations

import argparse
import json
import statistics
from glob import glob
from pathlib import Path
from typing import Any, Iterable


DEFAULT_PREFIXES = (
    "total_ms_",
    "verify_phase_ms_",
    "verify_artifact_ms_",
    "verify_checks_",
    "suite_store_manifest_",
    "overhead_ms_",
    "postsolve_",
    "solve_model_ms_",
    "solve_bvps_",
    "bvps_cache_",
    "bvps_persist_",
)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}"


def _load_metrics(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        metrics = payload.get("metrics", {})
        if isinstance(metrics, dict):
            return metrics
    return {}


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


def rollup_reports(
    report_paths: Iterable[Path], prefixes: Iterable[str] | None = None
) -> dict[str, dict[str, float]]:
    prefix_list = tuple(prefixes) if prefixes else DEFAULT_PREFIXES
    values_by_key: dict[str, list[float]] = {}
    for path in report_paths:
        metrics = _load_metrics(path)
        for key, value in metrics.items():
            if not isinstance(key, str):
                continue
            if not any(key.startswith(prefix) for prefix in prefix_list):
                continue
            if not _is_number(value):
                continue
            values_by_key.setdefault(key, []).append(float(value))
    results: dict[str, dict[str, float]] = {}
    for key, values in values_by_key.items():
        if not values:
            continue
        n = len(values)
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values) if n > 1 else 0.0
        results[key] = {
            "n": float(n),
            "mean": mean,
            "stdev": stdev,
            "min": min(values),
            "max": max(values),
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Roll up suite report metrics.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Metric key prefix to include (repeatable).",
    )
    args = parser.parse_args()

    prefixes = args.prefix if args.prefix else None
    report_paths = _expand_inputs(args.reports)
    results = rollup_reports(report_paths, prefixes=prefixes)
    for key in sorted(results):
        stats = results[key]
        print(
            f"{key} "
            f"n={int(stats['n'])} "
            f"mean={_format_number(stats['mean'])} "
            f"stdev={_format_number(stats['stdev'])} "
            f"min={_format_number(stats['min'])} "
            f"max={_format_number(stats['max'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
