from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _write_history(path: Path, prev: dict, curr: dict) -> None:
    path.write_text(
        json.dumps(prev, separators=(",", ":"))
        + "\n"
        + json.dumps(curr, separators=(",", ":"))
        + "\n"
    )


def test_perf_guard_smoke(tmp_path: Path) -> None:
    history = tmp_path / "perf_history.jsonl"
    prev = {
        "timestamp": "t1",
        "default_report": "prev.json",
        "default_metrics": {
            "total_ms_p95": 100,
            "total_ms_p99": 120,
            "verify_phase_ms_p99": 50,
            "verify_artifact_ms_p95": 20,
        },
    }
    curr = {
        "timestamp": "t2",
        "default_report": "curr.json",
        "default_metrics": {
            "total_ms_p95": 120,
            "total_ms_p99": 150,
            "verify_phase_ms_p99": 70,
            "verify_artifact_ms_p95": 25,
        },
    }
    _write_history(history, prev, curr)

    env = dict(os.environ)
    env["PERF_GUARD_TOTAL_P95_PCT"] = "10"
    env["PERF_GUARD_TOTAL_P99_PCT"] = "15"
    env["PERF_GUARD_VERIFY_P99_PCT"] = "15"
    env["PERF_GUARD_VERIFY_ARTIFACT_P95_PCT"] = "15"
    cmd = [sys.executable, "tools/perf_guard.py", "--path", str(history)]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 1

    env["PERF_GUARD_TOTAL_P95_PCT"] = "30"
    env["PERF_GUARD_TOTAL_P99_PCT"] = "30"
    env["PERF_GUARD_VERIFY_P99_PCT"] = "50"
    env["PERF_GUARD_VERIFY_ARTIFACT_P95_PCT"] = "50"
    result_ok = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert result_ok.returncode == 0
