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


def _solve_breakdown_sum(breakdown: dict[str, object]) -> int:
    total = 0
    for key in (
        "solve_task_load_ms",
        "solve_model_ms",
        "solve_bvps_cache_lookup_ms",
        "solve_bvps_fastpath_ms",
        "solve_other_ms",
    ):
        total += int(breakdown.get(key, 0))
    return total


def test_solve_breakdown_accounting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    task = _load_task(Path("examples/tasks/bvps_abs_01.json"))
    result = controller.run(task=task, mode=mode)
    payload = json.loads(result.ucr_path.read_text())

    costs = payload.get("costs", {})
    assert isinstance(costs, dict)
    breakdown = costs.get("solve_breakdown_ms")
    assert isinstance(breakdown, dict)
    for key in (
        "solve_task_load_ms",
        "solve_model_ms",
        "solve_bvps_cache_lookup_ms",
        "solve_bvps_fastpath_ms",
        "solve_other_ms",
    ):
        value = breakdown.get(key)
        assert isinstance(value, int)
        assert value >= 0

    phase_ms = costs.get("phase_ms", {})
    assert isinstance(phase_ms, dict)
    solve_ms = int(phase_ms.get("solve", 0))
    assert abs(solve_ms - _solve_breakdown_sum(breakdown)) <= 1


def test_solve_breakdown_cache_hit_skip_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")

    clock = {"t": 0.0}

    def fake_perf_counter() -> float:
        clock["t"] += 0.002
        return clock["t"]

    monkeypatch.setattr(
        "eidolon_v16.orchestrator.controller.time.perf_counter", fake_perf_counter
    )

    task = _load_task(Path("examples/tasks/bvps_abs_01.json"))
    mode = ModeConfig(seed=0, use_gpu=False)

    base_config = default_config(root=tmp_path / "base")
    base_controller = EpisodeController(config=base_config)
    base_controller.run(task=task, mode=mode)
    base_result = base_controller.run(task=task, mode=mode)
    base_payload = json.loads(base_result.ucr_path.read_text())
    base_breakdown = base_payload.get("costs", {}).get("solve_breakdown_ms", {})
    assert isinstance(base_breakdown, dict)
    assert int(base_breakdown.get("solve_bvps_cache_lookup_ms", 0)) > 0
    assert int(base_breakdown.get("solve_task_load_ms", 0)) > 0
    assert "solve_model_ms" in base_breakdown

    monkeypatch.setenv("EIDOLON_BVPS_CACHE_SKIP_MODEL", "1")
    skip_config = default_config(root=tmp_path / "skip")
    skip_controller = EpisodeController(config=skip_config)
    skip_controller.run(task=task, mode=mode)
    skip_result = skip_controller.run(task=task, mode=mode)
    skip_payload = json.loads(skip_result.ucr_path.read_text())
    skip_breakdown = skip_payload.get("costs", {}).get("solve_breakdown_ms", {})
    assert isinstance(skip_breakdown, dict)
    assert int(skip_breakdown.get("solve_bvps_cache_lookup_ms", 0)) > 0
    assert int(skip_breakdown.get("solve_task_load_ms", 0)) == 0
    assert int(skip_breakdown.get("solve_model_ms", 0)) <= 1
