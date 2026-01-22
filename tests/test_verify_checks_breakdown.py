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


def test_verify_checks_breakdown(
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
    verify_checks = costs.get("verify_checks_ms")
    assert isinstance(verify_checks, dict)
    assert "verify_task_verifier_ms" in verify_checks
    assert "verify_other_ms" in verify_checks

    verify_breakdown = costs.get("verify_breakdown_ms", {})
    assert isinstance(verify_breakdown, dict)
    verify_artifact_ms = int(verify_breakdown.get("verify_artifact_ms", 0))
    checks_sum = sum(int(value) for value in verify_checks.values())
    assert verify_artifact_ms >= checks_sum
