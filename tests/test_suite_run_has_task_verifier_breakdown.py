from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_suite_run_has_task_verifier_breakdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: task-verifier-detail",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    runs = payload.get("runs", [])
    assert isinstance(runs, list)
    run = runs[0]
    detail = run.get("verify_task_verifier_detail_ms")
    assert isinstance(detail, dict)
    assert "verify_task_verifier_detail_tv_exec_ms" in run
