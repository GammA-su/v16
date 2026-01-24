from __future__ import annotations

import argparse
import json
from glob import glob
from pathlib import Path
from typing import Any, Iterable


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


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, dict) else {}


def _match_keys(keys: list[str], prefix: str | None, suffixes: list[str]) -> list[str]:
    matched = []
    for key in keys:
        if prefix and not key.startswith(prefix):
            continue
        if suffixes and not any(key.endswith(suffix) for suffix in suffixes):
            continue
        matched.append(key)
    return matched


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate report.json keys and meta.")
    parser.add_argument("reports", nargs="+", help="report.json paths or globs")
    parser.add_argument("--require-prefix", action="append", default=[])
    parser.add_argument("--require-suffix", action="append", default=[])
    parser.add_argument("--show-meta", action="store_true")
    args = parser.parse_args()

    report_paths = _expand_inputs(args.reports)
    require_prefixes = list(args.require_prefix)
    require_suffixes = list(args.require_suffix)
    missing_any = False

    for path in report_paths:
        if not path.exists():
            print(f"{path} missing file")
            missing_any = True
            continue
        report = _load_report(path)
        metrics = report.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        keys = sorted([str(key) for key in metrics.keys() if isinstance(key, str)])
        missing_prefixes: list[str] = []
        status = "ok"
        if require_prefixes:
            for prefix in require_prefixes:
                prefix_only = _match_keys(keys, prefix, [])
                prefix_suffix = _match_keys(keys, prefix, require_suffixes)
                if not prefix_suffix:
                    missing_prefixes.append(
                        f"{prefix} (prefix={len(prefix_only)} prefix+suffix={len(prefix_suffix)})"
                    )
        if missing_prefixes:
            status = "missing matching keys for prefix+suffix: " + ", ".join(
                missing_prefixes
            )
            missing_any = True
        suite_dir = path.parent.name
        print(f"{suite_dir} {status}")
        if args.show_meta:
            meta = report.get("report_meta", {})
            if not isinstance(meta, dict):
                meta = {}
            print(
                "  "
                f"created_utc={meta.get('created_utc','')} "
                f"git_sha={meta.get('git_sha','')} "
                f"git_dirty={meta.get('git_dirty','')} "
                f"host={meta.get('host','')} "
                f"pid={meta.get('pid','')}"
            )
    return 2 if missing_any else 0


if __name__ == "__main__":
    raise SystemExit(main())
