from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite
from eidolon_v16.orchestrator import controller as controller_module


def test_artifact_plan_sink_off_skips_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: artifact-plan-off-skip",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )

    def _boom(_: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("should not be called")

    monkeypatch.setattr(controller_module, "_build_artifact_plan", _boom)
    monkeypatch.setenv("ARTIFACT_PLAN_SINK", "off")
    monkeypatch.setenv("ARTIFACT_PLAN_TMPFS_DIR", str(tmp_path / "tmpfs"))
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.setenv("EIDOLON_GGUF", "")

    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    run = payload["runs"][0]
    run_dir = Path(run["run_dir"])
    assert not (run_dir / "artifact_plan.json").exists()
    tmpfs_dir = tmp_path / "tmpfs"
    if tmpfs_dir.exists():
        assert not list(tmpfs_dir.rglob("artifact_plan.json"))
    assert run.get("postsolve_artifact_plan_detail_artifact_plan_build_ms") == 0
    assert run.get("postsolve_artifact_plan_detail_artifact_plan_serialize_ms") == 0
    assert run.get("postsolve_artifact_plan_detail_artifact_plan_write_ms") == 0
