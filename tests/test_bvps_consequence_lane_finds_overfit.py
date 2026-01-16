from __future__ import annotations

from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.verify.lanes import run_consequence


def test_bvps_consequence_lane_finds_overfit(tmp_path: Path) -> None:
    oracle = bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict()
    spec = {
        "name": "x_plus_one",
        "inputs": [["x", "Int"]],
        "output": "Int",
        "examples": [{"in": {"x": 0}, "out": 0}, {"in": {"x": 1}, "out": 1}],
        "bounds": {"int_range": {"min": -2, "max": 2}, "fuzz_trials": 5},
        "oracle": oracle,
    }
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-overfit",
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

    verdict = run_consequence(task, solution, store, seed=0)
    assert verdict.status == "FAIL"
    evidence = store.read_json_by_hash(verdict.evidence[0].hash)
    assert evidence.get("counterexample") is not None
