from __future__ import annotations

from pathlib import Path

from eidolon_v16.eval import suite as suite_mod


def test_suite_simple_yaml_scalar_items() -> None:
    text = "\n".join(
        [
            "suite_name: bvps-abs-only",
            "seeds: [0,1,2,3]",
            "tasks:",
            "  - bvps_abs_01",
            "",
        ]
    )
    spec = suite_mod._load_suite_yaml(text.encode("utf-8"), Path("suite.yaml"))
    assert spec.suite_name == "bvps-abs-only"
    assert spec.seeds == [0, 1, 2, 3]
    assert [task.name for task in spec.tasks] == ["bvps_abs_01"]
