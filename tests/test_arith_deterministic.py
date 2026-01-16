from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import Interpretation, TaskInput
from eidolon_v16.kernel.base import SolutionCandidate


class FailingKernel:
    def propose_interpretations(self, task: TaskInput, *, seed: int) -> list[Interpretation]:
        return [
            Interpretation(
                interpretation_id="arith-test",
                description="Test interpretation",
                assumptions=[],
                ambiguity_slots=[],
            )
        ]

    def propose_solution(self, task: TaskInput, interpretation: Interpretation, *, seed: int):
        raise AssertionError("kernel propose_solution should not be called for arith")

    def critique(self, task: TaskInput, solution, *, seed: int) -> str:
        return ""


def test_arith_uses_safe_eval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    kernel = FailingKernel()
    monkeypatch.setattr(controller, "_select_kernel", lambda store: kernel)

    task = TaskInput.from_raw(
        {
            "task_id": "arith-test",
            "kind": "arith",
            "prompt": "Compute 2 + 3 * 4",
            "data": {"expression": "2 + 3 * 4"},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0))

    ucr_payload = json.loads(result.ucr_path.read_text())
    assert ucr_payload["final_result"] == "result=14"

    store = ArtifactStore(config.paths.artifact_store)
    solution_hash = ucr_payload["solution_artifacts"][0]["hash"]
    solution_payload = store.read_json_by_hash(solution_hash)
    assert solution_payload["output"] == 14
    assert isinstance(solution_payload["output"], int)


def test_build_solution_payload_canonicalizes_string(tmp_path: Path) -> None:
    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "arith-string",
            "kind": "arith",
            "prompt": "Compute 2 + 3 * 4",
            "data": {"expression": "2 + 3 * 4"},
        }
    )
    solution = SolutionCandidate(output="14", solution_kind="arith_eval")
    payload = controller._build_solution_payload(task, solution)
    assert payload["output"] == 14
    assert isinstance(payload["output"], int)
