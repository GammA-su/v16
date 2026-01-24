from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "report_outliers", Path("scripts/report_outliers.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_report(path: Path, runs: list[dict]) -> None:
    path.write_text(json.dumps({"runs": runs}))


def test_report_outliers_smoke(tmp_path: Path) -> None:
    report1 = tmp_path / "r1.json"
    report2 = tmp_path / "r2.json"

    _write_report(
        report1,
        [
            {"task": "t1", "seed": 0, "verify_phase_ms": 5, "total_ms": 10},
            {"task": "t2", "seed": 0, "verify_phase_ms": 15, "total_ms": 20},
        ],
    )
    _write_report(
        report2,
        [
            {"task": "t1", "seed": 0, "verify_phase_ms": 25, "total_ms": 30},
            {"task": "t2", "seed": 0, "verify_phase_ms": 12, "total_ms": 22},
        ],
    )

    module = _load_module()
    outliers, _filtered, _total = module.collect_outliers(
        [report1, report2], "verify_phase_ms", ["total_ms"]
    )
    assert outliers[0]["task"] == "t1"
    assert outliers[0]["metric"] == 25
    formatted = (
        f"{outliers[0]['metric']} task={outliers[0]['task']} seed={outliers[0]['seed']}"
    )
    assert "task=" in formatted
