from __future__ import annotations

from pathlib import Path

from eidolon_v16.skills.registry import get_skill, register_skill
from eidolon_v16.skills.spec import SkillImpl, SkillSpec, TriggerSpec


def test_skill_registry_roundtrip(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    bundle_dir = tmp_path / "skills" / "x_plus_one" / "v0"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    spec = SkillSpec(
        name="x_plus_one",
        version="v0",
        created_ts_utc="2024-01-01T00:00:00Z",
        origin_episode_id="ep-1",
        triggers=TriggerSpec(task_contains=["x_plus_one"], task_family="bvps"),
        io_schema={"inputs": [{"name": "x", "type": "Int"}], "output": "Int"},
        preconditions={"bounds": {"int_range": {"min": -2, "max": 2}}},
        verifier_profile={"lanes": ["translation"], "require_all": True},
        cost_profile={"cpu_ms": 0, "steps": 10},
        impl=SkillImpl(
            kind="bvps_ast",
            program={"type": "var", "name": "x"},
            dsl_version="bvps/v1",
        ),
        artifacts=[],
    )
    register_skill(registry_path, spec, bundle_dir)
    record = get_skill(registry_path, "x_plus_one")
    assert record is not None
    assert record.spec.name == "x_plus_one"
