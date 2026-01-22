from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.eval.suite import run_suite


def _write_suite(path: Path) -> None:
    task_one = Path("examples/tasks/arith_01.json").resolve()
    task_two = Path("examples/tasks/arith_edge_01.json").resolve()
    path.write_text(
        "\n".join(
            [
                "suite_name: manifest-flush",
                "tasks:",
                "  - name: arith_01",
                f"    path: {task_one}",
                "  - name: arith_edge_01",
                f"    path: {task_two}",
                "seeds:",
                "  - 0",
            ]
        )
    )


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


def test_suite_manifest_flush_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite_path = tmp_path / "suite.yaml"
    _write_suite(suite_path)
    config = default_config(root=tmp_path)
    calls = {"count": 0}
    original = ArtifactStore.write_manifest

    def _wrapped(self: ArtifactStore, manifest: object) -> None:
        calls["count"] += 1
        original(self, manifest)

    monkeypatch.setattr(ArtifactStore, "write_manifest", _wrapped)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    report_payload = json.loads(report.report_path.read_text())

    runs = report_payload.get("runs", [])
    assert isinstance(runs, list)
    for run in runs:
        if not isinstance(run, dict):
            continue
        verify_breakdown = run.get("verify_breakdown_ms", {})
        if not isinstance(verify_breakdown, dict):
            continue
        store_ms = verify_breakdown.get("verify_store_ms", {})
        if isinstance(store_ms, dict):
                assert int(store_ms.get("manifest_ms", 0)) <= 5

    metrics = report_payload.get("metrics", {})
    assert isinstance(metrics, dict)
    assert int(metrics.get("suite_store_manifest_flush_ms", 0)) > 0
    assert metrics.get("store_manifest_flush_mode") == "per_suite"
    assert int(metrics.get("suite_store_manifest_flush_count", 0)) == 1
    assert calls["count"] == 1
    for key in (
        "suite_store_manifest_flush_detail_manifest_prepare_ms_p95",
        "suite_store_manifest_flush_detail_manifest_serialize_ms_p95",
        "suite_store_manifest_flush_detail_manifest_write_ms_p95",
    ):
        assert key in metrics

    manifest_path = config.paths.artifact_store / "manifest.json"
    assert manifest_path.exists()


def test_manifest_flush_per_episode_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_MANIFEST_BATCH", "1")

    calls = {"count": 0}
    original = ArtifactStore.write_manifest

    def _wrapped(self: ArtifactStore, manifest: object) -> None:
        calls["count"] += 1
        original(self, manifest)

    monkeypatch.setattr(ArtifactStore, "write_manifest", _wrapped)

    config = default_config(root=tmp_path)
    store = ArtifactStore(config.paths.artifact_store)
    store.set_manifest_flush_mode("per_episode")
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    task_one = _load_task(Path("examples/tasks/arith_01.json"))
    task_two = _load_task(Path("examples/tasks/arith_edge_01.json"))
    controller.run(task=task_one, mode=mode, store=store)
    controller.run(task=task_two, mode=ModeConfig(seed=1, use_gpu=False), store=store)

    assert calls["count"] == 2
