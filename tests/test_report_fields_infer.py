from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "report_fields", Path("scripts/report_fields.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_fields_infer() -> None:
    module = _load_module()
    payload = {
        "task": "t1",
        "seed": 3,
        "spec": {"name": "t2", "seed": 4},
        "item": {"task": "t3", "seed": 5},
    }
    assert module.infer_task(payload) == "t1"
    assert module.infer_seed(payload) == 3
    assert module.get_field(payload, "spec.name") == "t2"
    assert module.get_field(payload, "item.task") == "t3"
