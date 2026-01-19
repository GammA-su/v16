from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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
