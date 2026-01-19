from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_inspect_verify_overhead_report_top_one(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "runs": [
                    {"task": "slow", "total_ms": 50, "run_dir": "runs/ep-slow"},
                    {"task": "fast", "total_ms": 10, "run_dir": "runs/ep-fast"},
                ]
            }
        )
    )

    cmd = [
        sys.executable,
        str(Path("scripts") / "inspect_verify_overhead.py"),
        "--report",
        str(report_path),
        "--top",
        "1",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "rank=1" in result.stdout
    assert "total_ms=50" in result.stdout
