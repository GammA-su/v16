from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _write_report(path: Path, metrics: dict) -> None:
    path.write_text(json.dumps({"metrics": metrics}))


def test_report_rollup_smoke(tmp_path: Path) -> None:
    report1 = tmp_path / "r1.json"
    report2 = tmp_path / "r2.json"
    report3 = tmp_path / "r3.json"

    _write_report(report1, {"total_ms_mean": 10, "overhead_ms_p95": 2})
    _write_report(report2, {"total_ms_mean": 20, "overhead_ms_p95": 4})
    _write_report(report3, {"total_ms_mean": 30, "overhead_ms_p95": 6})

    spec = importlib.util.spec_from_file_location(
        "report_rollup", Path("scripts/report_rollup.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    results = module.rollup_reports([report1, report2, report3])
    total_stats = results["total_ms_mean"]
    overhead_stats = results["overhead_ms_p95"]

    assert int(total_stats["n"]) == 3
    assert total_stats["mean"] == 20
    assert total_stats["min"] == 10
    assert total_stats["max"] == 30

    assert int(overhead_stats["n"]) == 3
    assert overhead_stats["mean"] == 4
    assert overhead_stats["min"] == 2
    assert overhead_stats["max"] == 6
