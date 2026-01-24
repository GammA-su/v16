from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_report_variance_glob(tmp_path: Path) -> None:
    report_dir1 = tmp_path / "r1"
    report_dir2 = tmp_path / "r2"
    report_dir1.mkdir()
    report_dir2.mkdir()
    report1 = report_dir1 / "report.json"
    report2 = report_dir2 / "report.json"
    report1.write_text(
        json.dumps({"metrics": {"total_ms_mean": 10}, "runs": []})
    )
    report2.write_text(
        json.dumps({"metrics": {"total_ms_mean": 20}, "runs": []})
    )

    cmd = [
        sys.executable,
        str(Path("scripts/report_variance.py")),
        str(tmp_path / "r*" / "report.json"),
        "--metric-prefix",
        "total_ms_",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "Top metric variance" in result.stdout
