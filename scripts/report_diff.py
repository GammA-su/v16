from __future__ import annotations

import argparse
import json
from glob import glob
from pathlib import Path
from typing import Any

from eidolon_v16.cli_utils import sanitize_ansi_path


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_report(path: str) -> dict[str, Any]:
    payload = json.loads(Path(sanitize_ansi_path(path)).read_text())
    if isinstance(payload, dict):
        return payload
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


def _numeric_metrics(metrics: dict[str, Any]) -> dict[str, int]:
    numeric: dict[str, int] = {}
    for key, value in metrics.items():
        if isinstance(value, bool):
            continue
        value_int = _as_int(value)
        if value_int is None:
            continue
        numeric[str(key)] = value_int
    return numeric


def _flatten_run(run: dict[str, Any]) -> dict[str, int]:
    flat: dict[str, int] = {}
    total_ms = _as_int(run.get("total_ms"))
    if total_ms is not None:
        flat["total_ms"] = total_ms
    overhead_ms = _as_int(run.get("overhead_ms"))
    if overhead_ms is not None:
        flat["overhead_ms"] = overhead_ms
    phase_ms = run.get("phase_ms")
    if isinstance(phase_ms, dict):
        verify_ms = _as_int(phase_ms.get("verify"))
        if verify_ms is not None:
            flat["verify_phase_ms"] = verify_ms
    overhead_breakdown = run.get("overhead_breakdown_ms")
    if isinstance(overhead_breakdown, dict):
        postsolve_ms = _as_int(overhead_breakdown.get("overhead_postsolve_ms"))
        if postsolve_ms is not None:
            flat["postsolve_ms"] = postsolve_ms
    solve_breakdown = run.get("solve_breakdown_ms")
    if isinstance(solve_breakdown, dict):
        for key, value in solve_breakdown.items():
            value_int = _as_int(value)
            if value_int is None:
                continue
            flat[str(key)] = value_int
    verify_checks = run.get("verify_checks_ms")
    if isinstance(verify_checks, dict):
        for key, value in verify_checks.items():
            value_int = _as_int(value)
            if value_int is None:
                continue
            flat[f"verify_check_{key}"] = value_int
    return flat


def _run_key(run: dict[str, Any]) -> tuple[str, str]:
    task = str(run.get("task") or run.get("task_id") or "")
    seed = str(run.get("seed", ""))
    return task, seed


def _cache_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"hit:mem": 0, "hit:persist": 0, "miss:none": 0}
    for run in runs:
        cache = run.get("bvps_cache")
        cache_state = ""
        if isinstance(cache, str):
            cache_state = cache
        elif isinstance(cache, dict):
            hit = "hit" if cache.get("hit") else "miss"
            scope = str(cache.get("scope") or "none")
            cache_state = f"{hit}:{scope}"
        if cache_state in counts:
            counts[cache_state] += 1
        elif cache_state:
            counts.setdefault(cache_state, 0)
            counts[cache_state] += 1
        else:
            counts["miss:none"] += 1
    return counts


def _persist_info(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics", {})
    suite_meta = report.get("suite_meta", {})
    if not isinstance(metrics, dict):
        metrics = {}
    if not isinstance(suite_meta, dict):
        suite_meta = {}
    info: dict[str, Any] = {}
    for key, value in metrics.items():
        if key.startswith("bvps_persist_"):
            info[key] = value
    info.setdefault(
        "bvps_persist_disable_reason", suite_meta.get("bvps_persist_disable_reason", "")
    )
    return info


def _print_metric_deltas(base: dict[str, int], new: dict[str, int], top: int) -> None:
    rows = []
    for key in sorted(set(base) | set(new)):
        a = base.get(key, 0)
        b = new.get(key, 0)
        delta = b - a
        if delta == 0:
            continue
        rows.append((abs(delta), key, a, b, delta))
    rows.sort(reverse=True)
    print("Top metric deltas")
    if not rows:
        print("  (no metric deltas)")
        return
    for _abs_delta, key, a, b, delta in rows[:top]:
        print(f"  {key} {a} -> {b} (delta {delta:+})")


def _print_run_deltas(
    base_runs: dict[tuple[str, str], dict[str, int]],
    new_runs: dict[tuple[str, str], dict[str, int]],
    sort_key: str | None,
    top: int,
) -> None:
    rows = []
    for key in sorted(set(base_runs) & set(new_runs)):
        a = base_runs[key]
        b = new_runs[key]
        delta = {}
        for field in set(a) | set(b):
            delta[field] = b.get(field, 0) - a.get(field, 0)
        primary_key = sort_key or "total_ms"
        primary_delta = delta.get(primary_key, 0)
        rows.append((abs(primary_delta), primary_delta, key, a, b, delta))
    rows.sort(reverse=True)
    print("Top run deltas (matched by task+seed)")
    if not rows:
        print("  (no matched runs)")
        return
    for _abs_delta, primary_delta, key, a, b, delta in rows[:top]:
        task, seed = key
        focus_key = sort_key or "total_ms"
        focus_delta = delta.get(focus_key, 0)
        print(f"  {task} seed={seed} {focus_key} {a.get(focus_key,0)} -> {b.get(focus_key,0)} (delta {focus_delta:+})")
        extra_fields = ["overhead_ms", "verify_phase_ms", "postsolve_ms"]
        for field in extra_fields:
            if field == focus_key:
                continue
            if field in delta and delta[field] != 0:
                print(f"    {field} {a.get(field,0)} -> {b.get(field,0)} (delta {delta[field]:+})")
        ranked = []
        for field, value in delta.items():
            if field in extra_fields or field == focus_key:
                continue
            if value != 0:
                ranked.append((abs(value), field, value))
        ranked.sort(reverse=True)
        for _abs, field, value in ranked[:3]:
            print(f"    {field} {a.get(field,0)} -> {b.get(field,0)} (delta {value:+})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=str)
    parser.add_argument("new", type=str)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--sort", type=str, default=None)
    args = parser.parse_args()

    base_paths = _expand_inputs([args.base])
    new_paths = _expand_inputs([args.new])
    if len(base_paths) != 1 or len(new_paths) != 1:
        print("report_diff expects exactly one base and one new report after expansion")
        raise SystemExit(2)
    base_report = _load_report(str(base_paths[0]))
    new_report = _load_report(str(new_paths[0]))

    base_metrics = _numeric_metrics(base_report.get("metrics", {}) if isinstance(base_report.get("metrics"), dict) else {})
    new_metrics = _numeric_metrics(new_report.get("metrics", {}) if isinstance(new_report.get("metrics"), dict) else {})
    _print_metric_deltas(base_metrics, new_metrics, args.top)

    base_runs_raw = base_report.get("runs", [])
    new_runs_raw = new_report.get("runs", [])
    base_runs: dict[tuple[str, str], dict[str, int]] = {}
    new_runs: dict[tuple[str, str], dict[str, int]] = {}
    if isinstance(base_runs_raw, list):
        for run in base_runs_raw:
            if not isinstance(run, dict):
                continue
            base_runs[_run_key(run)] = _flatten_run(run)
    if isinstance(new_runs_raw, list):
        for run in new_runs_raw:
            if not isinstance(run, dict):
                continue
            new_runs[_run_key(run)] = _flatten_run(run)
    _print_run_deltas(base_runs, new_runs, args.sort, args.top)

    base_cache = _cache_counts(base_runs_raw if isinstance(base_runs_raw, list) else [])
    new_cache = _cache_counts(new_runs_raw if isinstance(new_runs_raw, list) else [])
    print("Cache delta summary")
    for key in sorted(set(base_cache) | set(new_cache)):
        a = base_cache.get(key, 0)
        b = new_cache.get(key, 0)
        delta = b - a
        print(f"  {key} {a} -> {b} (delta {delta:+})")

    base_persist = _persist_info(base_report)
    new_persist = _persist_info(new_report)
    print("Persist delta")
    for key in sorted(set(base_persist) | set(new_persist)):
        a = base_persist.get(key)
        b = new_persist.get(key)
        if a is None and b is None:
            continue
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            a_val = _as_int(a) or 0
            b_val = _as_int(b) or 0
            delta = b_val - a_val
            print(f"  {key} {a_val} -> {b_val} (delta {delta:+})")
        else:
            print(f"  {key} {a or ''} -> {b or ''}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
