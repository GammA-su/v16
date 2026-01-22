from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def test_bvps_persist_cache_hit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_payload = json.loads(Path("examples/tasks/bvps_abs_01.json").read_text())
    task = TaskInput.from_raw(task_payload)
    mode = ModeConfig(seed=0, use_gpu=False)

    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "1")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_DIR", str(tmp_path / "persist"))
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")
    config = default_config(root=tmp_path / "root")

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs1"))
    first = EpisodeController(config=config).run(task=task, mode=mode)
    first_payload = json.loads(first.ucr_path.read_text())
    first_cache = first_payload.get("costs", {}).get("bvps_cache", {})
    assert isinstance(first_cache, dict)
    assert first_cache.get("hit") is False

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs2"))
    second = EpisodeController(config=config).run(task=task, mode=mode)
    second_payload = json.loads(second.ucr_path.read_text())
    second_cache = second_payload.get("costs", {}).get("bvps_cache", {})
    assert isinstance(second_cache, dict)
    assert second_cache.get("hit") is True
    assert second_cache.get("scope") == "persist"
    assert second_payload.get("costs", {}).get("bvps_cache_state") == "hit:persist"
