from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def test_arith_stub_episode_outputs_numeric(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "arith-stub",
            "kind": "arith",
            "prompt": "Compute 2 + 3 * 4",
            "data": {"expression": "2 + 3 * 4"},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    ucr_payload = json.loads(result.ucr_path.read_text())
    statuses = [lane["status"] for lane in ucr_payload["verification"]]
    assert all(status == "PASS" for status in statuses)

    store = ArtifactStore(config.paths.artifact_store)
    solution_hash = ucr_payload["solution_artifacts"][0]["hash"]
    solution_payload = store.read_json_by_hash(solution_hash)
    output = solution_payload["output"]
    assert isinstance(output, (int, float))
    assert not isinstance(output, bool)

    costs = ucr_payload["costs"]
    assert costs["solve_wall_ms"] >= 0
    verifier = costs["verifier_ms"]
    assert isinstance(verifier["translation"], int)
    total_bytes = sum(entry["bytes"] for entry in ucr_payload["artifact_manifest"])
    assert costs["artifact_bytes"] == total_bytes
