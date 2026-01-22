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


def test_overhead_postsolve_detail_accounting(
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
    overhead_breakdown = costs.get("overhead_breakdown_ms", {})
    assert isinstance(overhead_breakdown, dict)
    postsolve_bucket = int(overhead_breakdown.get("overhead_postsolve_ms", 0))
    detail = overhead_breakdown.get("postsolve_detail_ms", {})
    assert isinstance(detail, dict)
    artifact_plan_detail = overhead_breakdown.get("postsolve_artifact_plan_detail_ms", {})
    assert isinstance(artifact_plan_detail, dict)

    keys = [
        "postsolve_prepare_inputs_ms",
        "postsolve_cache_touch_ms",
        "postsolve_artifact_plan_ms",
        "postsolve_policy_ms",
        "postsolve_misc_ms",
    ]
    for key in keys:
        assert key in detail
        value = int(detail.get(key, 0))
        assert value >= 0

    detail_sum = sum(int(detail.get(key, 0)) for key in keys)
    assert detail_sum <= postsolve_bucket + 5

    plan_keys = [
        "artifact_plan_serialize_ms",
        "artifact_plan_write_ms",
        "artifact_plan_fsync_ms",
        "artifact_plan_misc_ms",
    ]
    for key in plan_keys:
        assert key in artifact_plan_detail
        value = int(artifact_plan_detail.get(key, 0))
        assert value >= 0
    plan_sum = sum(int(artifact_plan_detail.get(key, 0)) for key in plan_keys)
    plan_total = int(detail.get("postsolve_artifact_plan_ms", 0))
    assert plan_sum <= plan_total + 5
