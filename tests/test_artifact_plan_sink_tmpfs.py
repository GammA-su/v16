from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_artifact_plan_sink_tmpfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: artifact-plan-tmpfs",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    tmpfs_dir = tmp_path / "tmpfs"
    monkeypatch.setenv("ARTIFACT_PLAN_SINK", "tmpfs")
    monkeypatch.setenv("ARTIFACT_PLAN_TMPFS_DIR", str(tmpfs_dir))
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))

    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    run = payload["runs"][0]
    run_dir = Path(run["run_dir"])
    assert not (run_dir / "artifact_plan.json").exists()
    expected = tmpfs_dir / "suite_artifacts" / Path(run["run_dir"]).name / "artifact_plan.json"
    assert expected.exists()
    assert isinstance(
        run.get("postsolve_artifact_plan_detail_artifact_plan_build_ms"), int
    )
    assert isinstance(
        run.get("postsolve_artifact_plan_detail_artifact_plan_serialize_ms"), int
    )
    assert isinstance(
        run.get("postsolve_artifact_plan_detail_artifact_plan_write_ms"), int
    )
