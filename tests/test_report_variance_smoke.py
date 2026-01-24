from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _write_report(path: Path, metrics: dict, runs: list[dict]) -> None:
    path.write_text(json.dumps({"metrics": metrics, "runs": runs}))


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "report_variance", Path("scripts/report_variance.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_variance_smoke(tmp_path: Path) -> None:
    report1 = tmp_path / "r1.json"
    report2 = tmp_path / "r2.json"
    report3 = tmp_path / "r3.json"

    _write_report(
        report1,
        {"total_ms_mean": 10, "verify_phase_ms_p95": 2},
        [
            {"task": "arith_01", "seed": 0, "total_ms": 10, "verify_phase_ms": 2},
            {"task": "arith_02", "seed": 0, "total_ms": 20, "verify_phase_ms": 4},
        ],
    )
    _write_report(
        report2,
        {"total_ms_mean": 20, "verify_phase_ms_p95": 2},
        [
            {"task": "arith_01", "seed": 0, "total_ms": 30, "verify_phase_ms": 2},
            {"task": "arith_02", "seed": 0, "total_ms": 21, "verify_phase_ms": 4},
        ],
    )
    _write_report(
        report3,
        {"total_ms_mean": 30, "verify_phase_ms_p95": 2},
        [
            {"task": "arith_01", "seed": 0, "total_ms": 50, "verify_phase_ms": 2},
            {"task": "arith_02", "seed": 0, "total_ms": 22, "verify_phase_ms": 4},
        ],
    )

    module = _load_module()
    metric_rows = module._metric_variance(
        [json.loads(report1.read_text()), json.loads(report2.read_text()), json.loads(report3.read_text())],
        ["total_ms_", "verify_phase_ms_"],
    )
    metric_rows.sort(key=lambda row: (row[3], row[2]), reverse=True)
    assert metric_rows[0][0] == "total_ms_mean"

    task_rows, _unknown, _total, missing = module._task_variance(
        [json.loads(report1.read_text()), json.loads(report2.read_text()), json.loads(report3.read_text())],
        "total_ms",
        group_mode="task+seed",
    )
    assert missing == 0
    task_rows.sort(key=lambda row: (row[3], row[2]), reverse=True)
    assert task_rows[0][0].startswith("arith_01 seed=")
