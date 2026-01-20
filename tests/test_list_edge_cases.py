from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps.synth import spec_function
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput

LIST_EDGE_TASKS = [
    "examples/tasks/list_edge_01.json",
    "examples/tasks/list_edge_02.json",
    "examples/tasks/list_edge_03.json",
    "examples/tasks/list_edge_04.json",
    "examples/tasks/list_edge_05.json",
]


@pytest.mark.parametrize("task_path", LIST_EDGE_TASKS)
def test_list_edge_cases(
    tmp_path: Path, task_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)

    payload = json.loads(Path(task_path).read_text())
    task = TaskInput.from_raw(payload)
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    ucr_payload = json.loads(result.ucr_path.read_text())
    statuses = [lane["status"] for lane in ucr_payload["verification"]]
    assert all(status == "PASS" for status in statuses)

    store = ArtifactStore(config.paths.artifact_store)
    solution_hash = ucr_payload["solution_artifacts"][0]["hash"]
    solution_payload = store.read_json_by_hash(solution_hash)

    operation = str(task.normalized.get("data", {}).get("operation", "sum"))
    input_list = task.normalized.get("data", {}).get("input", [])
    expected = spec_function(operation)([int(x) for x in input_list])
    assert solution_payload["output"] == expected
