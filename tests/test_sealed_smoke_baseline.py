from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


def _run_sealed(tmp_runs: Path) -> tuple[str, Path]:
    env = os.environ.copy()
    env["EIDOLON_RUNS_DIR"] = str(tmp_runs)
    env["EIDOLON_KERNEL"] = "stub"
    env["EIDOLON_GGUF"] = ""
    env.pop("EIDOLON_AUTO_SKILLS", None)

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
    commit_match = re.search(r"^Commitment:\s*([0-9a-f]{64})\s*$", stdout, re.MULTILINE)
    if not commit_match:
        raise AssertionError(f"commitment not found in output:\n{stdout}")

    report_path: str | None = None
    lines = stdout.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("Sealed eval report:"):
            tail = line.split("Sealed eval report:", 1)[1].strip()
            parts = [tail] if tail else []
            for extra in lines[idx + 1 :]:
                if extra.startswith("Commitment:") or extra.startswith("Seed:"):
                    break
                if extra.strip():
                    parts.append(extra.strip())
            candidate = "".join(parts).strip()
            if candidate:
                report_path = candidate
            break
    if report_path is None:
        raise AssertionError(f"report path not found in output:\n{stdout}")
    return commit_match.group(1), Path(report_path)


def test_sealed_smoke_commitment_and_passes(tmp_path: Path) -> None:
    commitment, report_path = _run_sealed(tmp_path / "runs")
    baseline_commitment = Path("baselines/sealed-smoke.commitment.txt").read_text().strip()
    assert commitment == baseline_commitment

    report_text = report_path.read_text()
    if not report_text:
        raise AssertionError("sealed report missing")
    results = json.loads(report_text).get("results", [])
    assert results
    for result in results:
        verdict = str(result.get("verdict", "")).lower()
        assert verdict == "pass"
        ucr_path = Path(str(result.get("ucr_path", "")))
        assert ucr_path.exists()
        ucr_payload = json.loads(ucr_path.read_text())
        lane_verdicts = ucr_payload.get("lane_verdicts", {})
        assert isinstance(lane_verdicts, dict)
        assert lane_verdicts
        for lane_verdict in lane_verdicts.values():
            assert isinstance(lane_verdict, dict)
            status = str(lane_verdict.get("status", "")).upper()
            assert status == "PASS"
