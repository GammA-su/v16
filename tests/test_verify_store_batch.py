from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def test_verify_store_ms_present_in_batch_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_MANIFEST_BATCH", "1")

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    raw = json.loads(Path("examples/tasks/arith_01.json").read_text())
    task = TaskInput.from_raw(raw)
    result = controller.run(task=task, mode=mode)
    payload = json.loads(result.ucr_path.read_text())

    costs = payload.get("costs", {})
    assert isinstance(costs, dict)
    breakdown = costs.get("verify_breakdown_ms")
    assert isinstance(breakdown, dict)
    store_ms = breakdown.get("verify_store_ms")
    assert isinstance(store_ms, dict)
    for key in ("hash_ms", "blob_write_ms", "manifest_ms"):
        value = store_ms.get(key)
        assert isinstance(value, int)
        assert value >= 0
