from __future__ import annotations

from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.skills.compile import compile_skill_from_bvps
from eidolon_v16.ucr.models import LaneVerdict, TaskInput


def test_skill_compiles_from_verified_bvps(tmp_path: Path) -> None:
    oracle = bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict()
    spec = {
        "name": "x_plus_one",
        "inputs": [["x", "Int"]],
        "output": "Int",
        "examples": [{"in": {"x": 2}, "out": 3}],
        "bounds": {"max_depth": 2, "max_programs": 100, "fuzz_trials": 2},
        "oracle": oracle,
    }
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-compile",
            "kind": "bvps",
            "prompt": "BVPS",
            "data": {"bvps_spec": spec},
        }
    )
    program = bvps_ast.Program(
        params=[("x", "Int")],
        body=bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)),
        return_type="Int",
    )
    solution = {
        "solution_kind": "bvps_program",
        "program": program.to_dict(),
        "bvps_spec": spec,
    }
    lanes = [
        LaneVerdict(lane="translation", status="PASS"),
        LaneVerdict(lane="consequence", status="PASS"),
    ]
    store = ArtifactStore(tmp_path / "artifact_store")

    bundle = compile_skill_from_bvps(
        task=task,
        solution=solution,
        lanes=lanes,
        store=store,
        episode_id="ep-compile",
        seed=0,
    )

    assert bundle is not None
    assert bundle.spec.name == "x_plus_one"
    assert bundle.tests.get("cases")
    assert any(ref.type.startswith("skill_spec") for ref in bundle.artifact_refs)
