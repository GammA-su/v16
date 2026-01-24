from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "report_variance", Path("scripts/report_variance.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_report(path: Path, runs: list[dict]) -> None:
    path.write_text(json.dumps({"runs": runs}))


def test_report_variance_any_metric(tmp_path: Path) -> None:
    report1 = tmp_path / "r1.json"
    report2 = tmp_path / "r2.json"
    report3 = tmp_path / "r3.json"

    _write_report(
        report1,
        [
            {
                "task": "t1",
                "seed": 0,
                "metrics": {"verify_check_verify_task_verifier_ms": 10},
            },
            {
                "task": "t2",
                "seed": 0,
                "metrics": {"verify_check_verify_task_verifier_ms": 20},
            },
        ],
    )
    _write_report(
        report2,
        [
            {
                "task": "t1",
                "seed": 0,
                "metrics": {"verify_check_verify_task_verifier_ms": 30},
            },
            {
                "task": "t2",
                "seed": 0,
                "metrics": {"verify_check_verify_task_verifier_ms": 21},
            },
        ],
    )
    _write_report(
        report3,
        [
            {
                "task": "t1",
                "seed": 0,
                "metrics": {"verify_check_verify_task_verifier_ms": 50},
            },
            {
                "task": "t2",
                "seed": 0,
                "metrics": {"verify_check_verify_task_verifier_ms": 19},
            },
        ],
    )

    module = _load_module()
    rows, _unknown, _total, missing = module._task_variance(
        [
            json.loads(report1.read_text()),
            json.loads(report2.read_text()),
            json.loads(report3.read_text()),
        ],
        "verify_check_verify_task_verifier_ms",
        group_mode="task+seed",
    )
    assert missing == 0
    rows.sort(key=lambda row: (row[3], row[2]), reverse=True)
    assert rows[0][0] == "t1 seed=0"
