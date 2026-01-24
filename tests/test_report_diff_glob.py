from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_report_diff_glob(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    new_dir = tmp_path / "new"
    base_dir.mkdir()
    new_dir.mkdir()
    base_report = base_dir / "report.json"
    new_report = new_dir / "report.json"
    base_report.write_text(json.dumps({"metrics": {"total_ms_mean": 10}, "runs": []}))
    new_report.write_text(json.dumps({"metrics": {"total_ms_mean": 20}, "runs": []}))

    cmd = [
        sys.executable,
        str(Path("scripts/report_diff.py")),
        str(tmp_path / "ba*" / "report.json"),
        str(tmp_path / "ne*" / "report.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "Top metric deltas" in result.stdout
