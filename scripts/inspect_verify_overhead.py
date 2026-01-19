from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

LANES = ("recompute", "translation", "consequence", "anchors")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    return {}


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
        value = verdict.get("cost_ms")
        cost = _as_int(value)
        if cost is None:
            continue
        totals[normalized] = totals.get(normalized, 0) + cost
    return totals


def _lane_ms_from_ucr(ucr: dict[str, Any]) -> dict[str, int]:
    lane_verdicts = ucr.get("lane_verdicts")
    if isinstance(lane_verdicts, (dict, list)):
        return _lane_ms_from_verdicts(lane_verdicts)
    verification = ucr.get("verification")
    if isinstance(verification, list):
        return _lane_ms_from_verdicts(verification)
    costs = ucr.get("costs")
    if isinstance(costs, dict):
        lane_ms = costs.get("lane_ms")
        if isinstance(lane_ms, dict):
            totals: dict[str, int] = {}
            for lane, value in lane_ms.items():
                normalized = _normalize_lane(lane)
                if not normalized:
                    continue
                cost = _as_int(value)
                if cost is None:
                    continue
                totals[normalized] = totals.get(normalized, 0) + cost
            return totals
    return {}


def _lane_evidence_types(ucr: dict[str, Any]) -> dict[str, list[str]]:
    lane_verdicts = ucr.get("lane_verdicts")
    items: list[tuple[str | None, Any]] = []
    if isinstance(lane_verdicts, dict):
        items = [(lane, verdict) for lane, verdict in lane_verdicts.items()]
    elif isinstance(lane_verdicts, list):
        items = [(None, verdict) for verdict in lane_verdicts]
    elif isinstance(ucr.get("verification"), list):
        items = [(None, verdict) for verdict in ucr.get("verification", [])]
    types: dict[str, list[str]] = {}
    for lane, verdict in items:
        if not isinstance(verdict, dict):
            continue
        normalized = _normalize_lane(lane or verdict.get("lane", ""))
        if not normalized:
            continue
        evidence = verdict.get("evidence") or []
        if not isinstance(evidence, list):
            continue
        seen: set[str] = set(types.get(normalized, []))
        for ref in evidence:
            if not isinstance(ref, dict):
                continue
            ref_type = ref.get("type")
            if isinstance(ref_type, str):
                seen.add(ref_type)
        types[normalized] = sorted(seen)
    return types


def _artifact_stats(artifacts_dir: Path) -> tuple[int | None, int | None, bool | None]:
    if not artifacts_dir.exists():
        return None, None, None
    count = 0
    total_bytes = 0
    attempt2 = False
    for path in artifacts_dir.rglob("*"):
        if not path.is_file():
            continue
        count += 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue
        if "attempt2" in path.name:
            attempt2 = True
    return count, total_bytes, attempt2


def _phase_verify_ms(ucr: dict[str, Any]) -> int | None:
    costs = ucr.get("costs")
    if not isinstance(costs, dict):
        return None
    phase_ms = costs.get("phase_ms")
    if not isinstance(phase_ms, dict):
        return None
    return _as_int(phase_ms.get("verify"))


def _total_ms(ucr: dict[str, Any], run_entry: dict[str, Any] | None = None) -> int | None:
    costs = ucr.get("costs")
    if isinstance(costs, dict):
        value = _as_int(costs.get("total_ms"))
        if value is not None:
            return value
    if run_entry:
        return _as_int(run_entry.get("total_ms"))
    return None


def _fmt_value(value: Any) -> str:
    return "?" if value is None else str(value)


def _lane_types_bits(types: dict[str, list[str]]) -> str:
    if not types:
        return "lane_types=?"
    parts = []
    for lane in LANES:
        if lane not in types:
            continue
        joined = "|".join(types[lane]) if types[lane] else "?"
        parts.append(f"{lane}:{joined}")
    return "lane_types=" + ",".join(parts) if parts else "lane_types=?"


def _summarize_run(run_dir: Path | None, run_entry: dict[str, Any] | None = None) -> str:
    ucr_payload: dict[str, Any] = {}
    if run_dir is not None:
        ucr_payload = _load_json(run_dir / "ucr.json")
    total_ms = _total_ms(ucr_payload, run_entry)
    verify_ms = _phase_verify_ms(ucr_payload)
    lane_ms = _lane_ms_from_ucr(ucr_payload)
    lane_sum = sum(lane_ms.values()) if lane_ms else None
    verify_minus_lane = (
        verify_ms - lane_sum if verify_ms is not None and lane_sum is not None else None
    )
    artifacts_dir = run_dir / "artifacts" if run_dir is not None else None
    count, total_bytes, attempt2 = (
        _artifact_stats(artifacts_dir) if artifacts_dir is not None else (None, None, None)
    )
    lane_types = _lane_evidence_types(ucr_payload)
    bits = [
        f"run={_fmt_value(str(run_dir) if run_dir else None)}",
        f"total_ms={_fmt_value(total_ms)}",
        f"verify_ms={_fmt_value(verify_ms)}",
        f"lane_ms_sum={_fmt_value(lane_sum)}",
        f"verify_minus_lane={_fmt_value(verify_minus_lane)}",
        f"attempt2={_fmt_value(attempt2)}",
        f"artifacts={_fmt_value(count)}",
        f"artifact_bytes={_fmt_value(total_bytes)}",
        _lane_types_bits(lane_types),
    ]
    return " ".join(bits)


def _run_dir_from_entry(run: dict[str, Any]) -> Path | None:
    for key in ("run_dir", "run"):
        value = run.get(key)
        if isinstance(value, str) and value:
            path = Path(value)
            if path.exists():
                return path
    return None


def _report_runs(report_path: Path, top: int) -> list[dict[str, Any]]:
    report = _load_json(report_path)
    runs = report.get("runs") or []
    if not isinstance(runs, list):
        return []
    items: list[tuple[int, dict[str, Any]]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        total_ms = _as_int(run.get("total_ms")) or 0
        items.append((total_ms, run))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return [run for _total, run in items[: max(0, top)]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, help="Path to runs/<ep> directory")
    parser.add_argument("--report", type=Path, help="Path to suite report.json")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    if args.run is None and args.report is None:
        print("error: must provide --run or --report")
        return 2

    if args.run is not None:
        print(_summarize_run(args.run))
        return 0

    runs = _report_runs(args.report, args.top)
    for idx, run in enumerate(runs, start=1):
        run_dir = _run_dir_from_entry(run)
        line = _summarize_run(run_dir, run_entry=run)
        print(f"rank={idx} {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
