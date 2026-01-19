from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def _write_suite_yaml(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "suite_name: smoke-suite",
                "tasks:",
                "  - name: arith_01",
                "    path: examples/tasks/arith_01.json",
                "  - name: bvps_abs_01",
                "    path: examples/tasks/bvps_abs_01.json",
                "seeds:",
                "  - 0",
            ]
        )
    )


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    values = sorted(values)
    idx = int((len(values) - 1) * 0.95)
    return values[idx]


def _latest_report_path(out_dir: Path) -> Path:
    report_path = out_dir / "report.json"
    if report_path.exists():
        return report_path
    reports = sorted(out_dir.rglob("report.json"), key=lambda path: path.stat().st_mtime)
    if reports:
        return reports[-1]
    raise AssertionError("suite report.json not found in out dir")


def test_suite_report_cli_metrics(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.yaml"
    _write_suite_yaml(suite_file)
    out_dir = tmp_path / "suite-out"

    env = dict(os.environ)
    env["EIDOLON_KERNEL"] = "stub"
    env["EIDOLON_GGUF"] = ""
    env["EIDOLON_RUNS_DIR"] = str(tmp_path / "runs")

    cmd = [
        sys.executable,
        "-m",
        "eidolon_v16.cli",
        "eval",
        "suite",
        "--suite",
        str(suite_file),
        "--out-dir",
        str(out_dir),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    report_path = out_dir / "report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    runs = report.get("runs", [])
    assert runs
    metrics = report.get("metrics", {})
    lane_ms_sum = metrics.get("lane_ms_sum", {})

    failing = 0
    for run in runs:
        lane_statuses = run.get("lane_statuses", {})
        if not lane_statuses or any(
            str(status).upper() != "PASS" for status in lane_statuses.values()
        ):
            failing += 1
    assert failing == 0

    totals: list[int] = []
    lane_totals = {lane: 0 for lane in ("recompute", "translation", "consequence", "anchors")}
    for run in runs:
        lane_ms = run.get("lane_ms", {})
        assert isinstance(lane_ms, dict)
        lane_verdicts = run.get("lane_verdicts", {})
        assert isinstance(lane_verdicts, dict)
        for lane in lane_totals:
            assert lane in lane_ms
            assert isinstance(lane_ms[lane], int)
            assert lane in lane_verdicts
            verdict = lane_verdicts[lane]
            assert isinstance(verdict, dict)
            assert isinstance(verdict.get("cost_ms"), int)
            lane_totals[lane] += lane_ms[lane]
        total_ms = run.get("total_ms")
        assert isinstance(total_ms, int)
        assert total_ms > 0
        totals.append(total_ms)

    assert all(value > 0 for value in lane_totals.values())
    for lane in ("recompute", "translation", "consequence", "anchors"):
        assert int(lane_ms_sum.get(lane, 0)) > 0

    p95 = _p95(totals)
    assert p95 < 60000


def test_suite_report_latest_out_dir(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        "\n".join(
            [
                "suite_name: latest-suite",
                "tasks:",
                "  - name: arith_01",
                "    path: examples/tasks/arith_01.json",
                "seeds:",
                "  - 0",
            ]
        )
    )
    out_dir = tmp_path / "suite-out"

    env = dict(os.environ)
    env["EIDOLON_KERNEL"] = "stub"
    env["EIDOLON_GGUF"] = ""
    env["EIDOLON_RUNS_DIR"] = str(tmp_path / "runs")

    cmd = [
        sys.executable,
        "-m",
        "eidolon_v16.cli",
        "eval",
        "suite",
        "--suite",
        str(suite_file),
        "--out-dir",
        str(out_dir),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    report_path = _latest_report_path(out_dir)
    report = json.loads(report_path.read_text())
    runs = report.get("runs", [])
    assert runs

    failing = 0
    totals: list[int] = []
    for run in runs:
        lane_statuses = run.get("lane_statuses") or {}
        if not lane_statuses or any(
            str(status).upper() != "PASS" for status in lane_statuses.values()
        ):
            failing += 1
        lane_ms = run.get("lane_ms", {})
        assert isinstance(lane_ms, dict)
        for lane in ("recompute", "translation", "consequence", "anchors"):
            assert lane in lane_ms
            assert isinstance(lane_ms[lane], int)
        total_ms = run.get("total_ms")
        assert isinstance(total_ms, int)
        assert total_ms > 0
        totals.append(total_ms)

    assert failing == 0
    assert _p95(totals) < 5000


def test_suite_report_lane_costs_not_forced_to_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        "\n".join(
            [
                "suite_name: lane-costs",
                "tasks:",
                "  - name: arith_01",
                "    path: examples/tasks/arith_01.json",
                "seeds:",
                "  - 0",
            ]
        )
    )
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))

    clock = {"t": 0.0}

    def fake_perf_counter() -> float:
        clock["t"] += 0.007
        return clock["t"]

    monkeypatch.setattr("eidolon_v16.verify.lanes.time.perf_counter", fake_perf_counter)
    monkeypatch.setattr("eidolon_v16.orchestrator.controller.time.perf_counter", fake_perf_counter)

    report = run_suite(default_config(root=tmp_path), suite_file, out_dir=tmp_path / "suite-out")
    payload = json.loads(report.report_path.read_text())
    run = payload["runs"][0]
    lane_verdicts = run.get("lane_verdicts", {})
    assert isinstance(lane_verdicts, dict)
    for lane in ("recompute", "translation", "consequence", "anchors"):
        assert lane in lane_verdicts
        verdict = lane_verdicts[lane]
        assert isinstance(verdict, dict)
        assert isinstance(verdict.get("cost_ms"), int)
    assert any(
        lane_verdicts[lane]["cost_ms"] != 1
        for lane in ("recompute", "translation", "consequence")
    )
