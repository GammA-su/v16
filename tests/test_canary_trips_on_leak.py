from __future__ import annotations

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.eval.generator_families.family_absmax import AbsMaxFamily
from eidolon_v16.skills.admission import run_canary_gate
from eidolon_v16.skills.bundle import SkillBundle
from eidolon_v16.skills.spec import SkillImpl, SkillSpec, TriggerSpec


def test_canary_trips_on_leak() -> None:
    family = AbsMaxFamily()
    token = family.canary_token
    program = bvps_ast.Program(
        params=[("x", "Int")],
        body=bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)),
        return_type="Int",
    )
    spec = SkillSpec(
        name="bundle_leak",
        version="v0",
        created_ts_utc="2024-01-01T00:00:00Z",
        origin_episode_id="ep-leak",
        triggers=TriggerSpec(task_contains=["bundle_leak"], task_family="bvps"),
        io_schema={"inputs": [{"name": "x", "type": "Int"}], "output": "Int"},
        preconditions={"bounds": {"int_range": {"min": -3, "max": 3}}},
        verifier_profile={"lanes": ["translation"], "require_all": True},
        cost_profile={"cpu_ms": 0, "steps": 10},
        impl=SkillImpl(
            kind="bvps_ast", program=program.to_dict(), dsl_version="bvps/v1"
        ),
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
            "note": token,
        },
        verify_profile={"lanes": ["translation"], "require_all": True},
        artifact_refs=[],
        bundle_name=spec.name,
    )

    canary = run_canary_gate(bundle, sealed_lite=[], tokens=[token])
    assert canary["status"] == "FAIL"
    assert token in canary["hits"]
