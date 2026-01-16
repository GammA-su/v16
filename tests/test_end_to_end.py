from __future__ import annotations

import json
from pathlib import Path

from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.canonical import compute_ucr_hash
from eidolon_v16.ucr.models import TaskInput


def test_episode_run_and_replay(tmp_path: Path) -> None:
    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "arith_test",
            "kind": "arith",
            "prompt": "Compute 1 + 2 * 3",
            "data": {"expression": "1 + 2 * 3"},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))
    assert result.ucr_path.exists()
    assert result.witness_path.exists()

    ucr_payload = json.loads(result.ucr_path.read_text())
    assert ucr_payload["hashes"]["ucr_hash"] == compute_ucr_hash(ucr_payload)
    assert not _contains_absolute_path(ucr_payload)
    result.witness_path.unlink()
    assert controller.replay(result.ucr_path)


def _contains_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        if "path" in value:
            return Path(str(value["path"])).is_absolute()
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return False
