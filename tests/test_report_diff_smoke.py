from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload))


def test_report_diff_smoke(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    new = tmp_path / "new.json"
    base_payload = {
        "metrics": {
            "total_ms_mean": 10,
            "overhead_ms_p95": 2,
            "bvps_persist_lookup_us_sum": 10,
        },
        "runs": [
            {
                "task": "arith_01",
                "seed": 0,
                "total_ms": 10,
                "overhead_ms": 1,
                "phase_ms": {"verify": 3},
                "overhead_breakdown_ms": {"overhead_postsolve_ms": 1},
                "solve_breakdown_ms": {"solve_model_ms": 2},
                "verify_checks_ms": {"verify_task_verifier_ms": 1},
                "bvps_cache": {"hit": False, "scope": "none"},
            }
        ],
    }
    new_payload = {
        "metrics": {
            "total_ms_mean": 20,
            "overhead_ms_p95": 4,
            "bvps_persist_lookup_us_sum": 25,
        },
        "runs": [
            {
                "task": "arith_01",
                "seed": 0,
                "total_ms": 20,
                "overhead_ms": 3,
                "phase_ms": {"verify": 6},
                "overhead_breakdown_ms": {"overhead_postsolve_ms": 2},
                "solve_breakdown_ms": {"solve_model_ms": 4},
                "verify_checks_ms": {"verify_task_verifier_ms": 2},
                "bvps_cache": {"hit": True, "scope": "mem"},
            }
        ],
    }
    _write_report(base, base_payload)
    _write_report(new, new_payload)

    cmd = [
        sys.executable,
        str(Path("scripts/report_diff.py")),
        str(base),
        str(new),
        "--top",
        "5",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Top metric deltas" in stdout
    assert "Top run deltas (matched by task+seed)" in stdout
    assert "Cache delta summary" in stdout
    assert "Persist delta" in stdout
    assert "lookup_us_sum" in stdout
