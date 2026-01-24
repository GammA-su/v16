from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from glob import glob
from pathlib import Path
from typing import Any, Iterable

import importlib.util


DEFAULT_PREFIXES = (
    "total_ms_",
    "verify_checks_",
    "verify_phase_ms_",
    "suite_store_manifest_",
    "overhead_ms_",
    "postsolve_",
)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, dict) else {}


def _load_report_fields():
    spec = importlib.util.spec_from_file_location(
        "report_fields", Path(__file__).with_name("report_fields.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("report_fields.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FIELDS = _load_report_fields()

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


def _metric_variance(
    reports: Iterable[dict[str, Any]], prefixes: Iterable[str]
) -> list[tuple[str, float, float, float, int]]:
    values_by_key: dict[str, list[float]] = defaultdict(list)
    for report in reports:
        metrics = report.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if not isinstance(key, str) or not any(
                key.startswith(prefix) for prefix in prefixes
            ):
                continue
            if not _is_number(value):
                continue
            values_by_key[key].append(float(value))

    rows: list[tuple[str, float, float, float, int]] = []
    for key, values in values_by_key.items():
        if not values:
            continue
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
        denom = mean if abs(mean) > 1e-9 else 1e-9
        cv = stdev / abs(denom)
        rows.append((key, mean, stdev, cv, len(values)))
    return rows


def _extract_runs(report: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("runs", "results", "items"):
        value = report.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _task_variance(
    reports: Iterable[dict[str, Any]],
    metric_key: str,
    *,
    group_mode: str,
    task_field: str | None = None,
    seed_field: str | None = None,
) -> tuple[list[tuple[str, float, float, float, int]], int, int, int]:
    values_by_task: dict[str, list[float]] = defaultdict(list)
    total_runs = 0
    unknown_task_runs = 0
    missing_metric_runs = 0
    for report in reports:
        for run in _extract_runs(report):
            total_runs += 1
            task_value = (
                _FIELDS.get_field(run, task_field)
                if task_field
                else _FIELDS.infer_task(run)
            )
            if not isinstance(task_value, str) or not task_value.strip():
                task_value = "<unknown>"
                unknown_task_runs += 1
            seed_value = (
                _FIELDS.get_field(run, seed_field)
                if seed_field
                else _FIELDS.infer_seed(run)
            )
            if group_mode == "task+seed":
                if seed_value is None:
                    continue
                key = f"{task_value} seed={seed_value}"
            else:
                key = task_value
            value = run.get(metric_key)
            if not _is_number(value):
                metrics = run.get("metrics")
                if isinstance(metrics, dict):
                    value = metrics.get(metric_key)
            if not _is_number(value):
                missing_metric_runs += 1
                continue
            values_by_task[key].append(float(value))
    rows: list[tuple[str, float, float, float, int]] = []
    for task_key, values in values_by_task.items():
        if len(values) < 2:
            continue
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)
        denom = mean if abs(mean) > 1e-9 else 1e-9
        cv = stdev / abs(denom)
        rows.append((task_key, mean, stdev, cv, len(values)))
    return rows, unknown_task_runs, total_runs, missing_metric_runs


def _format_float(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}"


def _print_metric_rows(rows: list[tuple[str, float, float, float, int]], top: int) -> None:
    rows_sorted = sorted(rows, key=lambda item: (item[3], item[2]), reverse=True)
    for key, mean, stdev, cv, count in rows_sorted[:top]:
        print(
            f"{key} n={count} mean={_format_float(mean)} "
            f"stdev={_format_float(stdev)} cv={_format_float(cv)}"
        )


def _print_task_rows(rows: list[tuple[str, float, float, float, int]], top: int) -> None:
    rows_sorted = sorted(rows, key=lambda item: (item[3], item[2]), reverse=True)
    for task, mean, stdev, cv, count in rows_sorted[:top]:
        print(
            f"{task} n={count} mean={_format_float(mean)} "
            f"stdev={_format_float(stdev)} cv={_format_float(cv)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Report variance across suite runs.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--metric-prefix", action="append", default=[])
    parser.add_argument("--task-metric", default=None)
    parser.add_argument(
        "--task-group",
        choices=("task", "task+seed"),
        default="task",
        help="Group task variance by task or task+seed.",
    )
    parser.add_argument("--task-field", default=None)
    parser.add_argument("--seed-field", default=None)
    args = parser.parse_args()

    prefixes = args.metric_prefix or list(DEFAULT_PREFIXES)
    report_paths = _expand_inputs(args.reports)
    reports = [_load_report(path) for path in report_paths]
    metric_rows = _metric_variance(reports, prefixes)
    print("Top metric variance")
    _print_metric_rows(metric_rows, args.top)
    if args.task_metric:
        task_rows, unknown_runs, total_runs, missing_metric_runs = _task_variance(
            reports,
            args.task_metric,
            group_mode=args.task_group,
            task_field=args.task_field,
            seed_field=args.seed_field,
        )
        print("Top task variance")
        print(
            f"task_groups={len(task_rows)} "
            f"unknown_task_runs={unknown_runs} "
            f"total_runs={total_runs} "
            f"missing_metric_runs={missing_metric_runs}"
        )
        if not task_rows:
            print("  (no task groups with >=2 samples)")
            return 0
        _print_task_rows(task_rows, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
