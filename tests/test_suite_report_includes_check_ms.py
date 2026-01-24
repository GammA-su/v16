from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_suite_report_includes_check_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: check-ms",
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
    assert isinstance(run.get("verify_check_verify_domain_ms"), int)
    assert isinstance(run.get("verify_check_verify_format_ms"), int)
    assert isinstance(run.get("verify_check_verify_task_verifier_ms"), int)
