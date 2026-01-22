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


def test_overhead_breakdown_accounting(
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
    total_ms = int(costs.get("total_ms", 0))
    lane_sum = int(costs.get("lane_sum_ms", 0))
    phase_sum = int(costs.get("phase_sum_ms", 0))
    overhead_ms = int(costs.get("overhead_ms", 0))
    expected_overhead = total_ms - phase_sum - lane_sum
    if expected_overhead < 0:
        expected_overhead = 0
    assert abs(overhead_ms - expected_overhead) <= 2

    breakdown = costs.get("overhead_breakdown_ms", {})
    assert isinstance(breakdown, dict)
    bucket_sum = 0
    for key in (
        "overhead_startup_ms",
        "overhead_postsolve_ms",
        "overhead_postverify_ms",
        "overhead_postcapsule_ms",
        "overhead_suite_meta_ms",
        "overhead_residual_ms",
    ):
        value = int(breakdown.get(key, 0))
        assert value >= 0
        bucket_sum += value
    assert overhead_ms >= bucket_sum - 2
