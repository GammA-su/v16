from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_postsolve_misc_detail_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: postsolve-misc-detail",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.setenv("EIDOLON_GGUF", "")

    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    run = payload["runs"][0]

    assert "postsolve_detail_postsolve_misc_ms" in run
    detail_keys = [
        key for key in run.keys() if key.startswith("postsolve_misc_detail_")
    ]
    assert len(detail_keys) >= 3
    detail_sum = sum(
        int(run[key]) for key in detail_keys if isinstance(run.get(key), int)
    )
    misc_total = int(run["postsolve_detail_postsolve_misc_ms"])
    assert abs(detail_sum - misc_total) <= 2
