from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_solution_sink_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: solution-sink-off",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    monkeypatch.setenv("SOLUTION_SINK", "off")
    monkeypatch.setenv("ARTIFACT_PLAN_SINK", "off")
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.setenv("EIDOLON_GGUF", "")

    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    run = payload["runs"][0]

    assert run.get("postsolve_misc_detail_misc_solution_store_ms") == 0
    assert int(run.get("postsolve_detail_postsolve_misc_ms", 0)) <= 50

    run_dir = Path(run["run_dir"])
    assert not list((run_dir / "artifacts").glob("solution-*.json"))
