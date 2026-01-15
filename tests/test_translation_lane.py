from __future__ import annotations

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.verify.lanes import run_translation


def test_translation_lane_fails_on_missing_fields(tmp_path) -> None:
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

    verdict = run_translation(task, chosen, solution, store, seed=0)
    assert verdict.status == "FAIL"
