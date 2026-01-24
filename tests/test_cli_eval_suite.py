from __future__ import annotations

import json
import os
import subprocess
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


def _tiny_suite_yaml(path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    task_path = repo_root / "examples" / "tasks" / "arith_01.json"
    path.write_text(
        "\n".join(
            [
                "suite_name: discovery-suite",
                "tasks:",
                "  - name: arith_01",
                f"    path: {task_path.as_posix()}",
                "seeds:",
                "  - 0",
            ]
        )
    )


def _suite_runner(tmp_path: Path) -> CliRunner:
    return CliRunner(
        env={
            "EIDOLON_RUNS_DIR": str(tmp_path / "runs"),
            "EIDOLON_KERNEL": "stub",
            "EIDOLON_GGUF": "",
        }
    )


def _extract_report_path(output: str, runs_dir: Path) -> Path:
    for line in output.splitlines():
        if "Suite report:" in line:
            candidate = line.split("Suite report:", 1)[1].strip()
            if candidate:
                return Path(candidate)
    suites_dir = runs_dir / "suites"
    if suites_dir.exists():
        reports = sorted(
            suites_dir.rglob("report.json"), key=lambda path: path.stat().st_mtime
        )
        if reports:
            return reports[-1]
    raise AssertionError("Suite report path not found in CLI output or runs dir")


def _assert_report(report_path: Path) -> None:
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["suite_name"] == "test-suite"
    assert len(report["seeds"]) == 2
    assert len(report["tasks"]) == 4
    assert len(report["runs"]) == 8
    lane_totals = {lane: 0 for lane in ("recompute", "translation", "consequence", "anchors")}
    for run in report["runs"]:
        assert run["lane_statuses"]["translation"] == "PASS"
        assert run["run_dir"]
        assert run["ucr_hash"]
        lane_ms = run.get("lane_ms", {})
        assert isinstance(lane_ms, dict)
        for lane in lane_totals:
            assert lane in lane_ms
            assert isinstance(lane_ms[lane], int)
            lane_totals[lane] += lane_ms[lane]
        lane_verdicts = run.get("lane_verdicts", {})
        assert isinstance(lane_verdicts, dict)
        for lane in lane_totals:
            assert lane in lane_verdicts
            verdict = lane_verdicts[lane]
            assert isinstance(verdict, dict)
            assert isinstance(verdict.get("cost_ms"), int)
    for lane, total in lane_totals.items():
        assert total > 0, f"expected lane_ms for {lane} to be non-zero"


def test_cli_eval_suite(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.yaml"
    _suite_yaml(suite_file, seeds=[0, 1])
    runner = _suite_runner(tmp_path)
    result = runner.invoke(app, ["eval", "suite", "--suite", str(suite_file)])
    assert result.exit_code == 0
    runs_dir = tmp_path / "runs"
    report_path = _extract_report_path(result.stdout, runs_dir)
    assert report_path.name == "report.json"
    assert str(report_path.resolve()).startswith(str(runs_dir.resolve()))
    _assert_report(report_path)


def test_cli_eval_suite_aliases(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.yaml"
    _suite_yaml(suite_file, seeds=[0, 1])
    runner = _suite_runner(tmp_path)
    result = runner.invoke(app, ["eval", "suite", "--suite-file", str(suite_file)])
    assert result.exit_code == 0
    _assert_report(_extract_report_path(result.stdout, tmp_path / "runs"))

    result = runner.invoke(app, ["eval", "suite", "run", "--suite", str(suite_file)])
    assert result.exit_code == 0
    _assert_report(_extract_report_path(result.stdout, tmp_path / "runs"))


def test_cli_eval_suite_module_entrypoint(tmp_path: Path) -> None:
    suite_file = tmp_path / "discovery-suite.yaml"
    _tiny_suite_yaml(suite_file)

    env = dict(os.environ)
    env["EIDOLON_KERNEL"] = "stub"
    env["EIDOLON_GGUF"] = ""
    env["EIDOLON_RUNS_DIR"] = str(tmp_path / "runs")

    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "eidolon_v16.cli",
        "eval",
        "suite",
        "--suite",
        "discovery-suite.yaml",
    ]
    result = subprocess.run(
        cmd,
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    report_path = _extract_report_path(result.stdout, tmp_path / "runs")
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["suite_name"] == "discovery-suite"
    assert len(report["tasks"]) == 1
