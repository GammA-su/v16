from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from eidolon_v16.cli import app


def _latest_run_dir(root: Path) -> Path:
    runs = sorted(root.iterdir())
    if not runs:
        raise AssertionError("no runs produced")
    return runs[-1]


def test_cli_arith_translation_passes(tmp_path: Path) -> None:
    runner = CliRunner(
        env={
            "EIDOLON_RUNS_DIR": str(tmp_path / "runs"),
            "EIDOLON_KERNEL": "stub",
        }
    )
    result = runner.invoke(
        app,
        [
            "run",
            "--task-file",
            str(Path("examples/tasks/arith_01.json").resolve()),
            "--seed",
            "0",
        ],
    )
    assert result.exit_code == 0
    run_dir = _latest_run_dir(tmp_path / "runs")
    ucr = json.loads((run_dir / "ucr.json").read_text())
    lane_verdicts = ucr["lane_verdicts"]
    assert lane_verdicts["translation"]["status"] == "PASS"
    assert all(lane["status"] == "PASS" for lane in lane_verdicts.values())
