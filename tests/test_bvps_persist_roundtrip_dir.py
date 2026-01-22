from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.bvps import cache as bvps_cache
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def test_bvps_persist_roundtrip_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "1")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_DIR", str(tmp_path / "persist"))
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")

    task_payload = json.loads(Path("examples/tasks/bvps_abs_01.json").read_text())
    task = TaskInput.from_raw(task_payload)
    mode = ModeConfig(seed=0, use_gpu=False)
    config = default_config(root=tmp_path / "root")

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs1"))
    EpisodeController(config=config).run(task=task, mode=mode)

    bvps_cache.reset_persist_stats()

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs2"))
    second = EpisodeController(config=config).run(task=task, mode=mode)
    payload = json.loads(second.ucr_path.read_text())
    cache = payload.get("costs", {}).get("bvps_cache", {})
    assert isinstance(cache, dict)
    assert cache.get("hit") is True
    assert cache.get("scope") == "persist"

    stats = bvps_cache.persist_stats_snapshot()
    assert int(stats.get("bvps_persist_reads", 0)) > 0
    assert int(stats.get("bvps_persist_lookups", 0)) > 0


def test_bvps_persist_disable_reason_env_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "0")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_DIR", str(tmp_path / "persist"))
    bvps_cache.reset_persist_stats()
    stats = bvps_cache.persist_stats_snapshot()
    assert stats.get("bvps_persist_enabled") is False
    assert stats.get("bvps_persist_disable_reason") == "env_off"
