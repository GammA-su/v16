from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.bvps import cache as bvps_cache
from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def test_bvps_persist_timing_stats_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "1")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_DIR", str(tmp_path / "persist"))
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")

    task_payload = json.loads(Path("examples/tasks/bvps_abs_01.json").read_text())
    task = TaskInput.from_raw(task_payload)
    mode = ModeConfig(seed=0, use_gpu=False)
    config = default_config(root=tmp_path / "root")

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs1"))
    EpisodeController(config=config).run(task=task, mode=mode)
    stats_write = bvps_cache.persist_stats_snapshot()
    assert int(stats_write.get("bvps_persist_writes", 0)) > 0
    assert int(stats_write.get("bvps_persist_write_us_sum", 0)) >= 0

    bvps_cache.reset_persist_stats()

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs2"))
    EpisodeController(config=config).run(task=task, mode=mode)
    stats_read = bvps_cache.persist_stats_snapshot()
    assert int(stats_read.get("bvps_persist_reads", 0)) > 0
    assert int(stats_read.get("bvps_persist_lookups", 0)) > 0
    assert int(stats_read.get("bvps_persist_read_us_sum", 0)) > 0
    assert int(stats_read.get("bvps_persist_lookup_us_sum", 0)) >= 0


def test_bvps_persist_timing_stats_report_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "1")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_DIR", str(tmp_path / "persist"))
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")

    task_payload = json.loads(Path("examples/tasks/bvps_abs_01.json").read_text())
    task = TaskInput.from_raw(task_payload)
    mode = ModeConfig(seed=0, use_gpu=False)
    config = default_config(root=tmp_path / "root")

    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs1"))
    EpisodeController(config=config).run(task=task, mode=mode)

    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: bvps-persist-report",
                "tasks:",
                "  - bvps_abs_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs2"))
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    metrics = payload.get("metrics", {})
    assert isinstance(metrics, dict)
    assert "bvps_persist_read_ns_sum" in metrics
    assert "bvps_persist_read_us_sum" in metrics
    reads = int(metrics.get("bvps_persist_reads", 0))
    if reads > 0:
        assert int(metrics.get("bvps_persist_read_ns_sum", 0)) > 0
        assert int(metrics.get("bvps_persist_read_us_sum", 0)) >= 1
