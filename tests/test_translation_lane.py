from __future__ import annotations

from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.verify.lanes import run_translation


def test_translation_lane_fails_on_missing_fields(tmp_path: Path) -> None:
    task = TaskInput.from_raw(
        {
            "task_id": "list_test",
            "kind": "list",
            "prompt": "Compute sum for the list.",
            "data": {"operation": "sum", "input": [1, 2]},
        }
    )
    kernel = StubKernel()
    interpretations = kernel.propose_interpretations(task, seed=0)
    interpretations.sort(key=lambda item: item.interpretation_id)
    chosen = interpretations[0]
    store = ArtifactStore(tmp_path / "artifact_store")
    solution = {
        "solution_kind": "bvps_program",
        "output": 3,
        "input": [1, 2],
    }

    verdict, _ = run_translation(task, chosen, solution, store, seed=0)
    assert verdict.status == "FAIL"


def test_translation_lane_passes_on_arith(tmp_path: Path) -> None:
    task = TaskInput.from_raw(
        {
            "task_id": "arith_test",
            "task": "ARITH: 2 + 3",
            "data": {"expression": "2 + 3"},
        }
    )
    kernel = StubKernel()
    interpretations = kernel.propose_interpretations(task, seed=0)
    interpretations.sort(key=lambda item: item.interpretation_id)
    chosen = interpretations[0]
    store = ArtifactStore(tmp_path / "artifact_store")
    solution = {
        "solution_kind": "arith_eval",
        "expression": "2 + 3",
        "output": 5,
    }

    verdict, _ = run_translation(task, chosen, solution, store, seed=0)
    assert verdict.status == "PASS"


def test_translation_lane_passes_on_arith_prompt_fallback(tmp_path: Path) -> None:
    task = TaskInput.from_raw(
        {
            "task_id": "arith_prompt_fallback",
            "task": "ARITH: 7 / 2",
        }
    )
    kernel = StubKernel()
    interpretations = kernel.propose_interpretations(task, seed=0)
    interpretations.sort(key=lambda item: item.interpretation_id)
    chosen = interpretations[0]
    store = ArtifactStore(tmp_path / "artifact_store")
    solution = {
        "solution_kind": "arith_eval",
        "output": 3.5,
    }

    verdict, _ = run_translation(task, chosen, solution, store, seed=0)
    assert verdict.status == "PASS"
