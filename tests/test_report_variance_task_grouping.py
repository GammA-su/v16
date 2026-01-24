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


def test_report_variance_task_grouping(tmp_path: Path) -> None:
    report1 = tmp_path / "r1.json"
    report2 = tmp_path / "r2.json"

    report1.write_text(
        json.dumps({"runs": [{"spec": {"name": "t1"}, "seed": 0, "total_ms": 10}]})
    )
    report2.write_text(
        json.dumps({"runs": [{"item": {"task": "t1"}, "seed": 1, "total_ms": 20}]})
    )

    module = _load_module()
    reports = [json.loads(report1.read_text()), json.loads(report2.read_text())]
    task_rows, _unknown, _total, missing = module._task_variance(
        reports, "total_ms", group_mode="task"
    )
    assert missing == 0
    assert task_rows
    task_seed_rows, _unknown2, _total2, missing2 = module._task_variance(
        reports, "total_ms", group_mode="task+seed"
    )
    assert missing2 == 0
    assert not task_seed_rows
