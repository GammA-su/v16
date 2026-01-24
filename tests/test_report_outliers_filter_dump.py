from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_report_outliers_filter_dump(tmp_path: Path) -> None:
    report_dir = tmp_path / "r1"
    report_dir.mkdir()
    report_path = report_dir / "report.json"
    runs = [
        {
            "task": "arith_01",
            "seed": 0,
            "total_ms": 10,
            "verify_checks_ms": {"verify_domain_ms": 1, "verify_format_ms": 2},
            "verify_task_verifier_detail_tv_exec_ms": 7,
        },
        {
            "task": "arith_02",
            "seed": 0,
            "total_ms": 20,
            "verify_checks_ms": {"verify_domain_ms": 3, "verify_format_ms": 4},
        },
    ]
    report_path.write_text(json.dumps({"runs": runs}))

    cmd = [
        sys.executable,
        str(Path("scripts/report_outliers.py")),
        str(tmp_path / "r1" / "report.json"),
        "--metric",
        "total_ms",
        "--where",
        "task=arith_01",
        "--field",
        "verify_task_verifier_detail_tv_exec_ms",
        "--dump-field",
        "verify_checks_ms",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    stdout = result.stdout.strip().splitlines()
    assert stdout
    assert "task=arith_01" in stdout[0]
    assert "verify_task_verifier_detail_tv_exec_ms=7" in stdout[0]
    assert stdout[1].startswith("  verify_checks_ms=")
