from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def test_report_meta_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: meta-check",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    meta = payload.get("report_meta", {})
    assert isinstance(meta, dict)
    for key in (
        "created_utc",
        "git_sha",
        "git_dirty",
        "host",
        "pid",
        "python",
        "config_flags",
    ):
        assert key in meta
    assert isinstance(meta.get("created_utc"), str)
    assert meta.get("created_utc")
    assert isinstance(meta.get("host"), str)
    assert meta.get("host")
    assert isinstance(meta.get("python"), str)
    assert meta.get("python")
    assert str(meta.get("pid")).isdigit()
    assert isinstance(meta.get("git_sha"), str)
    assert meta.get("git_sha")
