from pathlib import Path

from typer.testing import CliRunner

from eidolon_v16.cli import app


def test_cli_run_rejects_empty_task(tmp_path: Path) -> None:
    task_file = tmp_path / "empty.json"
    task_file.write_text("   \n")
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--task-file", str(task_file)])
    assert result.exit_code != 0
    assert "Task file is empty" in result.stdout
    assert "Traceback" not in result.stdout
