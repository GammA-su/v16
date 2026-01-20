from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


def test_verify_breakdown_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    task = _load_task(Path("examples/tasks/arith_01.json"))
    result = controller.run(task=task, mode=mode)
    payload = json.loads(result.ucr_path.read_text())

    costs = payload.get("costs", {})
    assert isinstance(costs, dict)
    breakdown = costs.get("verify_breakdown_ms")
    assert isinstance(breakdown, dict)
    for key in (
        "verify_lane_exec_ms",
        "verify_artifact_ms",
        "verify_admission_ms",
        "verify_store_ms",
        "verify_overhead_ms",
    ):
        value = breakdown.get(key)
        if key == "verify_store_ms":
            assert isinstance(value, dict)
            for store_key in ("hash_ms", "blob_write_ms", "manifest_ms"):
                store_value = value.get(store_key)
                assert isinstance(store_value, int)
                assert store_value >= 0
        else:
            assert isinstance(value, int)
            assert value >= 0

    phase_ms = costs.get("phase_ms", {})
    assert isinstance(phase_ms, dict)
    verify_ms = int(phase_ms.get("verify", 0))
    total = sum(value for value in breakdown.values() if isinstance(value, int))
    assert abs(verify_ms - total) <= 5
