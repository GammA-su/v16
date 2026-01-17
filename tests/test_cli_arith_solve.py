from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from eidolon_v16.cli import app
from eidolon_v16.utils import safe_eval_arith


def test_cli_arith_solution_succeeds(tmp_path: Path) -> None:
    task_payload = {"kind": "arith", "task": "ARITH: (13 + 1) * 2"}
    task_file = tmp_path / "arith.json"
    task_file.write_text(json.dumps(task_payload))
    runner = CliRunner(
        env={
            "EIDOLON_RUNS_DIR": str(tmp_path / "runs"),
            "EIDOLON_KERNEL": "stub",
        }
    )

    result = runner.invoke(app, ["run", "--task-file", str(task_file), "--seed", "0"])
    assert result.exit_code == 0

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert run_dirs, "expected episode run output"
    run_dir = run_dirs[-1]
    ucr = json.loads((run_dir / "ucr.json").read_text())
    statuses = [lane["status"] for lane in ucr["verification"]]
    assert all(status == "PASS" for status in statuses)

    artifacts_dir = run_dir / "artifacts"
    solution_files = sorted(artifacts_dir.glob("solution-*.json"))
    assert solution_files
    solution = json.loads(solution_files[0].read_text())
    expression = "(13 + 1) * 2"
    assert solution["expression"] == expression
    assert solution["output"] == safe_eval_arith(expression)

    capsule_files = list(artifacts_dir.glob("capsule_success-*.tar"))
    assert capsule_files
