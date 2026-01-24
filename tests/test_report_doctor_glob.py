from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_report_doctor_glob(tmp_path: Path) -> None:
    report_dir1 = tmp_path / "r1"
    report_dir2 = tmp_path / "r2"
    report_dir1.mkdir()
    report_dir2.mkdir()
    report1 = report_dir1 / "report.json"
    report2 = report_dir2 / "report.json"
    payload = {
        "metrics": {"verify_checks_verify_domain_count": 1},
        "report_meta": {
            "created_utc": "2026-01-01T00:00:00Z",
            "git_sha": "deadbeef",
            "git_dirty": False,
            "host": "localhost",
            "pid": 1,
            "python": "3.10.0",
            "config_flags": {},
        },
    }
    report1.write_text(json.dumps(payload))
    report2.write_text(json.dumps(payload))

    cmd = [
        sys.executable,
        str(Path("scripts/report_doctor.py")),
        str(tmp_path / "r*" / "report.json"),
        "--require-prefix",
        "verify_checks_",
        "--require-suffix",
        "_count",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "r1" in result.stdout
    assert "r2" in result.stdout
