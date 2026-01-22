from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


def _write_suite_yaml(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "suite_name: bvps-preload-suite",
                "tasks:",
                "  - name: bvps_abs_01",
                "    path: examples/tasks/bvps_abs_01.json",
                "seeds:",
                "  - 0",
                "  - 1",
            ]
        )
    )


def test_bvps_persist_preload_suite_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "1")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_PRELOAD", "1")
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_DIR", str(tmp_path / "persist"))

    config = default_config(root=tmp_path / "root")
    runs_dir = tmp_path / "runs"
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(runs_dir))

    task = _load_task(Path("examples/tasks/bvps_abs_01.json"))
    EpisodeController(config=config).run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    suite_path = tmp_path / "suite.yaml"
    _write_suite_yaml(suite_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    report_payload = json.loads(report.report_path.read_text())

    suite_meta = report_payload.get("suite_meta", {})
    assert isinstance(suite_meta, dict)
    assert _as_int(suite_meta.get("bvps_persist_preload_entries")) >= 1
    assert _as_int(suite_meta.get("bvps_persist_preload_ms")) > 0

    runs = report_payload.get("runs", [])
    assert isinstance(runs, list)
    for run in runs:
        assert isinstance(run, dict)
        assert "bvps_persist_preload_ms" not in run
        assert "bvps_persist_preload_entries" not in run
        if run.get("task") == "bvps_abs_01":
            assert run.get("bvps_cache") == "hit:mem"


def _as_int(value: object) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
