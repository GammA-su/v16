from __future__ import annotations

import argparse
import json
from glob import glob
from pathlib import Path
from typing import Any, Iterable

import importlib.util


Outlier = dict[str, Any]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _extract_runs(report: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("runs", "results", "items"):
        value = report.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


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

def _expand_inputs(items: Iterable[object]) -> list[Path]:
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


def _parse_filters(filters: Iterable[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for raw in filters:
        if "=" not in raw:
            raise ValueError(f"invalid filter: {raw}")
        key, value = [chunk.strip() for chunk in raw.split("=", 1)]
        parsed.append((key, value))
    return parsed


def _match_filters(
    run: dict[str, Any],
    filters: list[tuple[str, str]],
    *,
    task_field: str | None,
    seed_field: str | None,
) -> bool:
    for key, value in filters:
        if key == "task":
            candidate = (
                _FIELDS.get_field(run, task_field)
                if task_field
                else _FIELDS.infer_task(run)
            )
        elif key == "seed":
            candidate = (
                _FIELDS.get_field(run, seed_field)
                if seed_field
                else _FIELDS.infer_seed(run)
            )
        else:
            candidate = _FIELDS.get_field(run, key)
        if value == "None":
            if candidate is not None:
                return False
        else:
            if candidate is None:
                return False
            if str(candidate) != value:
                return False
    return True


def collect_outliers(
    report_paths: Iterable[Path],
    metric: str,
    fields: Iterable[str],
    where: list[str] | None = None,
    *,
    task_field: str | None = None,
    seed_field: str | None = None,
) -> tuple[list[Outlier], int, int]:
    outliers: list[Outlier] = []
    filters = _parse_filters(where or [])
    total_runs = 0
    filtered_runs = 0

    for path in report_paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            continue
        for run in _extract_runs(payload):
            total_runs += 1
            if filters and not _match_filters(
                run, filters, task_field=task_field, seed_field=seed_field
            ):
                continue
            filtered_runs += 1
            task_value = (
                _FIELDS.get_field(run, task_field)
                if task_field
                else _FIELDS.infer_task(run)
            )
            if not isinstance(task_value, str) or not task_value.strip():
                task_value = "<unknown>"
            seed_value = (
                _FIELDS.get_field(run, seed_field)
                if seed_field
                else _FIELDS.infer_seed(run)
            )
            value = run.get(metric)
            if not _is_number(value):
                metrics = run.get("metrics")
                if isinstance(metrics, dict):
                    value = metrics.get(metric)
            if not _is_number(value):
                continue
            field_values: dict[str, float] = {}
            for field in fields:
                field_value = run.get(field)
                if not _is_number(field_value):
                    metrics = run.get("metrics")
                    if isinstance(metrics, dict):
                        field_value = metrics.get(field)
                if _is_number(field_value):
                    field_values[field] = float(field_value)
            outliers.append(
                {
                    "metric": float(value),
                    "task": task_value,
                    "seed": int(seed_value)
                    if isinstance(seed_value, (int, float, str))
                    and str(seed_value).isdigit()
                    else None,
                    "report_path": str(path),
                    "fields": field_values,
                    "run": run,
                }
            )
    outliers.sort(
        key=lambda entry: (
            -entry["metric"],
            entry["task"],
            entry["seed"] if entry["seed"] is not None else -1,
            entry["report_path"],
        )
    )
    return outliers, filtered_runs, total_runs


def _format_field(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Find top per-run outliers.")
    parser.add_argument("reports", nargs="+", help="report.json paths or globs")
    parser.add_argument("--metric", required=True)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument(
        "--field",
        action="append",
        default=["total_ms", "verify_phase_ms"],
        help="Additional per-run metrics to print (repeatable).",
    )
    parser.add_argument(
        "--where",
        action="append",
        default=[],
        help="Filter like task=arith_01 or seed=0",
    )
    parser.add_argument(
        "--dump-field",
        action="append",
        default=[],
        help="Nested field to pretty-print for each outlier (repeatable).",
    )
    parser.add_argument("--task-field", default=None)
    parser.add_argument("--seed-field", default=None)
    args = parser.parse_args()

    report_paths = _expand_inputs(args.reports)
    outliers, filtered_runs, total_runs = collect_outliers(
        report_paths,
        args.metric,
        args.field,
        where=args.where,
        task_field=args.task_field,
        seed_field=args.seed_field,
    )
    if args.where and filtered_runs == 0:
        print(
            "no runs matched filters "
            f"{args.where} across {len(report_paths)} reports"
        )
        raise SystemExit(2)
    if not outliers:
        print(
            f"no runs matched metric={args.metric} "
            f"after filters (matched_runs={filtered_runs}, total_runs={total_runs})"
        )
        raise SystemExit(2)
    for entry in outliers[: args.top]:
        extras = " ".join(
            f"{name}={_format_field(value)}"
            for name, value in entry["fields"].items()
        )
        seed = entry["seed"] if entry["seed"] is not None else "?"
        print(
            f"{_format_field(entry['metric'])} "
            f"task={entry['task']} seed={seed} "
            f"{entry['report_path']} {extras}"
        )
        if args.dump_field:
            for dump_field in args.dump_field:
                if dump_field == "task":
                    dump_value = entry["task"]
                elif dump_field == "seed":
                    dump_value = entry["seed"]
                else:
                    dump_value = _FIELDS.get_field(entry["run"], dump_field)
                dump_json = json.dumps(
                    dump_value, sort_keys=True, separators=(",", ":")
                )
                print(f"  {dump_field}={dump_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
