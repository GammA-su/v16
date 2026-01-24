from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_report(path: Path, metrics: dict) -> None:
    payload = {
        "metrics": metrics,
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
    path.write_text(json.dumps(payload))


def test_report_doctor_smoke(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    _write_report(good, {"verify_checks_verify_domain_count": 1})
    _write_report(bad, {"verify_checks_verify_domain_ms_p95": 10})

    cmd = [
        sys.executable,
        str(Path("scripts/report_doctor.py")),
        str(good),
        str(bad),
        "--require-prefix",
        "verify_checks_",
        "--require-suffix",
        "_count",
        "--show-meta",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    stdout = result.stdout
    assert "missing" in stdout
