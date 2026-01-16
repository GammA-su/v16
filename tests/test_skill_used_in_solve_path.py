from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.skills.bundle import SkillBundle
from eidolon_v16.skills.registry import register_skill
from eidolon_v16.skills.spec import SkillImpl, SkillSpec, TriggerSpec
from eidolon_v16.skills.store import save_bundle
from eidolon_v16.ucr.models import TaskInput


def test_skill_used_in_solve_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    program = bvps_ast.Program(
        params=[("x", "Int")],
        body=bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)),
        return_type="Int",
    )
    spec = SkillSpec(
        name="x_plus_one",
        version="v0",
        created_ts_utc="2024-01-01T00:00:00Z",
        origin_episode_id="ep-1",
        triggers=TriggerSpec(task_contains=["x_plus_one"], task_family="bvps"),
        io_schema={"inputs": [{"name": "x", "type": "Int"}], "output": "Int"},
        preconditions={"bounds": {"int_range": {"min": -2, "max": 2}}},
        verifier_profile={"lanes": ["translation", "consequence"], "require_all": True},
        cost_profile={"cpu_ms": 0, "steps": 10},
        impl=SkillImpl(kind="bvps_ast", program=program.to_dict(), dsl_version="bvps/v1"),
        artifacts=[],
    )
    bundle = SkillBundle(
        spec=spec,
        program=program.to_dict(),
        tests={"fuzz_seed": 0, "fuzz_trials": 1, "cases": [], "oracle": None},
        verify_profile={"lanes": ["translation", "consequence"], "require_all": True},
        artifact_refs=[],
        bundle_name=spec.name,
    )

    config = default_config(root=tmp_path)
    bundle_dir = save_bundle(bundle, config.paths.skills_dir)
    register_skill(config.paths.skills_registry, spec, bundle_dir)

    spec_payload = {
        "name": "x_plus_one",
        "inputs": [["x", "Int"]],
        "output": "Int",
        "examples": [{"in": {"x": 2}, "out": 3}],
        "bounds": {"max_depth": 2, "max_programs": 200, "fuzz_trials": 2},
        "oracle": bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict(),
    }
    spec_json = json.dumps(spec_payload, separators=(",", ":"), sort_keys=True)
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-skill-use",
            "kind": "unknown",
            "prompt": f"BVPS_SPEC:{spec_json}",
            "data": {},
        }
    )
    controller = EpisodeController(config=config)
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    witness_payload = json.loads(result.witness_path.read_text())
    used_skill = witness_payload.get("used_skill")
    assert used_skill is not None
    assert used_skill.get("name") == "x_plus_one"
