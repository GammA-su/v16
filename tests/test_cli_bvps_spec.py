import json
from pathlib import Path

from typer.testing import CliRunner

from eidolon_v16.cli import app


def test_cli_bvps_prompt_runs(tmp_path: Path) -> None:
    task_file = tmp_path / "bvps.json"
    task_file.write_text(json.dumps({"task": "BVPS: abs(int)->int"}))
    run_root = tmp_path / "runs"
    runner = CliRunner(env={"EIDOLON_RUNS_DIR": str(run_root)})
    result = runner.invoke(app, ["episode", "run", "--task-file", str(task_file), "--seed", "0"])
    assert result.exit_code == 0
    episodes = sorted(run_root.iterdir())
    assert episodes, "episode run directory missing"
    run_dir = episodes[0]
    solution_files = sorted((run_dir / "artifacts").glob("solution-*.json"))
    assert solution_files, "solution artifact missing"
    solution = json.loads(solution_files[0].read_text())
    assert solution.get("solution_kind") in {"bvps_program", "skill_bvps"}
    assert solution.get("program") is not None
    trace = solution.get("trace", {}) or {}
    assert trace.get("bvps_report") or trace.get("used_skill") or solution.get("used_skill")
    ucr_payload = json.loads((run_dir / "ucr.json").read_text())
    lane = ucr_payload.get("lane_verdicts", {}).get("translation", {})
    assert lane.get("status") == "PASS"
