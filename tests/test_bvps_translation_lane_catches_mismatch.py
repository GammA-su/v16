from __future__ import annotations

from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.ucr.models import Interpretation, TaskInput
from eidolon_v16.verify.lanes import run_translation


def test_bvps_translation_lane_catches_mismatch(tmp_path: Path) -> None:
    spec = {
        "name": "add2",
        "inputs": [["x", "Int"], ["y", "Int"]],
        "output": "Int",
        "examples": [{"in": {"x": 1, "y": 2}, "out": 3}],
        "bounds": {"max_depth": 2, "max_programs": 100},
    }
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-translation",
            "kind": "bvps",
            "prompt": "BVPS",
            "data": {"bvps_spec": spec},
        }
    )
    program = bvps_ast.Program(
        params=[("x", "Int")],
        body=bvps_ast.Var("x"),
        return_type="Int",
    )
    solution = {"solution_kind": "bvps_program", "program": program.to_dict()}
    store = ArtifactStore(tmp_path / "artifacts")
    chosen = Interpretation(
        interpretation_id="bvps-spec", description="BVPS spec add2"
    )

    verdict, _ = run_translation(task, chosen, solution, store, seed=0)
    assert verdict.status == "FAIL"
