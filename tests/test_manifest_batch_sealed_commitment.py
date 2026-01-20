from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


def _run_sealed(tmp_runs: Path, *, manifest_batch: bool) -> str:
    env = os.environ.copy()
    env["EIDOLON_RUNS_DIR"] = str(tmp_runs)
    if manifest_batch:
        env["EIDOLON_MANIFEST_BATCH"] = "1"
    else:
        env.pop("EIDOLON_MANIFEST_BATCH", None)

    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "eidolon_v16.cli",
        "eval",
        "sealed",
        "--suite",
        "baselines/sealed-smoke.baseline.json",
        "--n",
        "10",
        "--seed",
        "0",
    ]
    result = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )
    stdout = result.stdout
    match = re.search(r"^Commitment:\s*([0-9a-f]{64})\s*$", stdout, re.MULTILINE)
    if match:
        return match.group(1)

    lines = [line.strip() for line in stdout.splitlines()]
    for idx, line in enumerate(lines):
        if line.startswith("Commitment:"):
            if idx + 1 < len(lines) and re.fullmatch(r"[0-9a-f]{64}", lines[idx + 1]):
                return lines[idx + 1]

    raise AssertionError(f"commitment not found in output:\n{stdout}")


def test_manifest_batch_sealed_commitment(tmp_path: Path) -> None:
    commitment_default = _run_sealed(tmp_path / "runs-default", manifest_batch=False)
    commitment_batch = _run_sealed(tmp_path / "runs-batch", manifest_batch=True)
    assert commitment_default == commitment_batch
