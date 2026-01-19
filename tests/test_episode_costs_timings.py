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


def _assert_costs(ucr_payload: dict[str, object]) -> None:
    costs = ucr_payload.get("costs", {})
    assert isinstance(costs, dict)
    assert int(costs.get("total_ms", 0)) > 0
    lane_ms = costs.get("lane_ms", {})
    assert isinstance(lane_ms, dict)
    for lane in ("recompute", "translation", "consequence", "anchors"):
        assert int(lane_ms.get(lane, 0)) >= 0
    verification = ucr_payload.get("verification", [])
    assert isinstance(verification, list)
    for lane in verification:
        if not isinstance(lane, dict):
            continue
        costs = lane.get("costs", {})
        assert isinstance(costs, dict)
        assert costs.get("ms") is not None


def test_episode_costs_include_phase_and_lane_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    arith_task = _load_task(Path("examples/tasks/arith_01.json"))
    bvps_task = _load_task(Path("examples/tasks/bvps_abs_01.json"))

    arith_result = controller.run(task=arith_task, mode=mode)
    bvps_result = controller.run(task=bvps_task, mode=mode)

    arith_payload = json.loads(arith_result.ucr_path.read_text())
    bvps_payload = json.loads(bvps_result.ucr_path.read_text())

    _assert_costs(arith_payload)
    _assert_costs(bvps_payload)


def test_lane_costs_use_measured_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))

    clock = {"t": 0.0}

    def fake_perf_counter() -> float:
        clock["t"] += 0.005
        return clock["t"]

    monkeypatch.setattr(
        "eidolon_v16.orchestrator.controller.time.perf_counter", fake_perf_counter
    )
    monkeypatch.setattr("eidolon_v16.verify.lanes.time.perf_counter", fake_perf_counter)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    arith_task = _load_task(Path("examples/tasks/arith_01.json"))
    result = controller.run(task=arith_task, mode=mode)

    payload = json.loads(result.ucr_path.read_text())
    lane_verdicts = payload.get("lane_verdicts", {})
    for lane in ("recompute", "translation", "consequence", "anchors"):
        verdict = lane_verdicts.get(lane, {})
        assert isinstance(verdict.get("cost_ms"), int)
        assert verdict.get("cost_ms", 0) >= 5
