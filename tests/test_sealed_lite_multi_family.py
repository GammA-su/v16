from __future__ import annotations

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.skills.admission import run_sealed_lite_gate
from eidolon_v16.skills.bundle import SkillBundle
from eidolon_v16.skills.spec import SkillImpl, SkillSpec, TriggerSpec


def _build_sample_bundle() -> SkillBundle:
    program = bvps_ast.Program(
        params=[("x", "Int")],
        body=bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)),
        return_type="Int",
    )
    spec = SkillSpec(
        name="x_plus_one",
        version="v0",
        created_ts_utc="2024-01-01T00:00:00Z",
        origin_episode_id="ep-test",
        triggers=TriggerSpec(task_contains=["x_plus_one"], task_family="bvps"),
        io_schema={"inputs": [{"name": "x", "type": "Int"}], "output": "Int"},
        preconditions={"bounds": {"int_range": {"min": -3, "max": 3}}},
        verifier_profile={"lanes": ["translation", "consequence"], "require_all": True},
        cost_profile={"cpu_ms": 0, "steps": 10},
        impl=SkillImpl(
            kind="bvps_ast", program=program.to_dict(), dsl_version="bvps/v1"
        ),
        artifacts=[],
    )
    return SkillBundle(
        spec=spec,
        program=program.to_dict(),
        tests={
            "fuzz_seed": 0,
            "fuzz_trials": 2,
            "cases": [{"in": {"x": 2}, "out": 3}],
            "oracle": bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict(),
        },
        verify_profile={"lanes": ["translation", "consequence"], "require_all": True},
        artifact_refs=[],
        bundle_name="x_plus_one",
    )


def test_sealed_lite_multi_family_passes() -> None:
    bundle = _build_sample_bundle()
    result = run_sealed_lite_gate(bundle, seed=0)
    assert result["status"] == "PASS"
    assert len(result["families"]) >= 2
    assert all(family["status"] == "PASS" for family in result["families"])
    assert result["canary_tokens"]
