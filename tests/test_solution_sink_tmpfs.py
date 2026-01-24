from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_solution_sink_tmpfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: solution-sink-tmpfs",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    tmpfs_dir = tmp_path / "shm"
    monkeypatch.setenv("SOLUTION_SINK", "tmpfs")
    monkeypatch.setenv("SOLUTION_TMPFS_DIR", str(tmpfs_dir))
    monkeypatch.setenv("ARTIFACT_PLAN_SINK", "off")
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.setenv("EIDOLON_GGUF", "")

    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    run = payload["runs"][0]

    solution_files = list(tmpfs_dir.glob("solution-*.json"))
    assert solution_files
    assert int(run.get("postsolve_misc_detail_misc_solution_store_ms", 0)) > 0
