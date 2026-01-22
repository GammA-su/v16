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


def test_overhead_manifest_detail_accounting(
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
    verify_breakdown = costs.get("verify_breakdown_ms", {})
    assert isinstance(verify_breakdown, dict)
    manifest_detail = verify_breakdown.get("verify_store_manifest_detail_ms", {})
    assert isinstance(manifest_detail, dict)
    manifest_total = int(verify_breakdown.get("verify_store_ms", {}).get("manifest_ms", 0))

    keys = [
        "manifest_prepare_ms",
        "manifest_hash_ms",
        "manifest_serialize_ms",
        "manifest_write_ms",
        "manifest_fsync_ms",
        "manifest_misc_ms",
    ]
    detail_sum = 0
    for key in keys:
        value = int(manifest_detail.get(key, 0))
        assert value >= 0
        detail_sum += value

    assert detail_sum <= manifest_total + 5
