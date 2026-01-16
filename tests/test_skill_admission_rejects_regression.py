from __future__ import annotations

from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.skills.admission import admit_skill
from eidolon_v16.skills.bundle import SkillBundle
from eidolon_v16.skills.spec import SkillImpl, SkillSpec, TriggerSpec


def test_skill_admission_rejects_regression(tmp_path: Path) -> None:
    program = bvps_ast.Program(
        params=[("x", "Int")],
        body=bvps_ast.Var("x"),
        return_type="Int",
    )
    spec = SkillSpec(
        name="x_plus_one",
        version="v0",
        created_ts_utc="2024-01-01T00:00:00Z",
        origin_episode_id="ep-1",
        triggers=TriggerSpec(task_contains=["x_plus_one"], task_family="bvps"),
        io_schema={"inputs": [{"name": "x", "type": "Int"}], "output": "Int"},
        preconditions={"bounds": {"int_range": {"min": -2, "max": 2}, "step_budget": 50}},
        verifier_profile={"lanes": ["translation", "consequence"], "require_all": True},
        cost_profile={"cpu_ms": 0, "steps": 50},
        impl=SkillImpl(kind="bvps_ast", program=program.to_dict(), dsl_version="bvps/v1"),
        artifacts=[],
    )
    bundle = SkillBundle(
        spec=spec,
        program=program.to_dict(),
        tests={
            "fuzz_seed": 0,
            "fuzz_trials": 1,
            "cases": [{"in": {"x": 1}, "out": 2}],
            "oracle": bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict(),
        },
        verify_profile={"lanes": ["translation", "consequence"], "require_all": True},
        artifact_refs=[],
        bundle_name=spec.name,
    )
    store = ArtifactStore(tmp_path / "artifact_store")

    result = admit_skill(bundle=bundle, store=store, seed=0)
    assert result.admitted is False
    assert result.evidence_ref is not None
