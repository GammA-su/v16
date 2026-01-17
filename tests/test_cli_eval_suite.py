from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from eidolon_v16.cli import app


def _suite_yaml(path: Path, seeds: list[int]) -> None:
    path.write_text(
        "\n".join(
            [
                "suite_name: test-suite",
                "tasks:",
                "  - name: arith_01",
                "    path: examples/tasks/arith_01.json",
                "  - name: bvps_abs_01",
                "    path: examples/tasks/bvps_abs_01.json",
                "  - name: bvps_max_01",
                "    path: examples/tasks/bvps_max_01.json",
                "  - name: bvps_even_01",
                "    path: examples/tasks/bvps_even_01.json",
                "seeds:",
            ]
            + [f"  - {seed}" for seed in seeds]
        )
    )


def test_cli_eval_suite(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.yaml"
    _suite_yaml(suite_file, seeds=[0, 1])
    runner = CliRunner(
        env={
            "EIDOLON_RUNS_DIR": str(tmp_path / "runs"),
            "EIDOLON_KERNEL": "stub",
            "EIDOLON_GGUF": "",
        }
    )
    result = runner.invoke(app, ["eval", "suite", "--suite", str(suite_file)])
    assert result.exit_code == 0
    compact_output = "".join(result.stdout.split())
    match = re.search(r"(/\S+artifact_store/sha256/\S+\.bin)", compact_output)
    assert match is not None
    report_path = Path(match.group(1))
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["suite_name"] == "test-suite"
    assert len(report["seeds"]) == 2
    assert len(report["tasks"]) == 4
    assert len(report["runs"]) == 8
    for run in report["runs"]:
        assert run["lane_statuses"]["translation"] == "PASS"
