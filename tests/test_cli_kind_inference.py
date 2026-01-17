import json
from pathlib import Path

from typer.testing import CliRunner

from eidolon_v16.cli import app


def test_cli_run_infers_arith_kind(tmp_path: Path) -> None:
    task_payload = {
        "task": "ARITH: 2 + 2",
        "data": {"expression": "2 + 2"},
    }
    task_file = tmp_path / "arith.json"
    task_file.write_text(json.dumps(task_payload))
    env = {"EIDOLON_RUNS_DIR": str(tmp_path / "runs")}
    runner = CliRunner(env=env)
    result = runner.invoke(app, ["run", "--task-file", str(task_file)])
    assert result.exit_code == 0
    run_root = tmp_path / "runs"
    entries = sorted(run_root.iterdir())
    assert entries, "expected episode run output"
    ucr_path = entries[0] / "ucr.json"
    payload = json.loads(ucr_path.read_text())
    assert payload["task_input"]["normalized"]["kind"] == "arith"
