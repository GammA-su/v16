from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_report_rollup_glob(tmp_path: Path) -> None:
    report_dir1 = tmp_path / "r1"
    report_dir2 = tmp_path / "r2"
    report_dir1.mkdir()
    report_dir2.mkdir()
    report1 = report_dir1 / "report.json"
    report2 = report_dir2 / "report.json"
    report1.write_text(json.dumps({"metrics": {"total_ms_mean": 10}}))
    report2.write_text(json.dumps({"metrics": {"total_ms_mean": 20}}))

    cmd = [
        sys.executable,
        str(Path("scripts/report_rollup.py")),
        str(tmp_path / "r*" / "report.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    output = result.stdout.strip().splitlines()
    assert output
    assert output[0].startswith("total_ms_mean")
