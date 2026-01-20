from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


def _lane_evidence_hashes(payload: dict[str, object]) -> dict[str, list[str]]:
    hashes: dict[str, list[str]] = {}
    verification = payload.get("verification", [])
    if not isinstance(verification, list):
        return hashes
    for lane in verification:
        if not isinstance(lane, dict):
            continue
        lane_name = str(lane.get("lane", ""))
        evidence = lane.get("evidence", [])
        if not isinstance(evidence, list):
            continue
        hashes[lane_name] = [
            str(ref.get("hash"))
            for ref in evidence
            if isinstance(ref, dict) and ref.get("hash") is not None
        ]
    return hashes


def _lane_evidence_payloads(
    payload: dict[str, object], store_root: Path
) -> dict[str, dict[str, object]]:
    store = ArtifactStore(store_root)
    payloads: dict[str, dict[str, object]] = {}
    verification = payload.get("verification", [])
    if not isinstance(verification, list):
        return payloads
    for lane in verification:
        if not isinstance(lane, dict):
            continue
        lane_name = str(lane.get("lane", ""))
        evidence = lane.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            continue
        ref = evidence[0]
        if not isinstance(ref, dict):
            continue
        content_hash = ref.get("hash")
        if not isinstance(content_hash, str) or not content_hash:
            continue
        payloads[lane_name] = store.read_json_by_hash(content_hash)
    return payloads


def test_manifest_batch_flush_writes_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_MANIFEST_BATCH", "1")
    store = ArtifactStore(tmp_path / "artifact_store")
    store.put_json({"a": 1}, artifact_type="test:a", producer="test")
    store.put_json({"b": 2}, artifact_type="test:b", producer="test")
    assert not store.manifest_path.exists()
    manifest = store.load_manifest()
    assert len(manifest.entries) == 2
    store.flush_manifest()
    assert store.manifest_path.exists()


def test_manifest_batch_keeps_lane_evidence_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    mode = ModeConfig(seed=0, use_gpu=False)

    def _run(label: str, batch: bool) -> dict[str, object]:
        monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / label / "runs"))
        if batch:
            monkeypatch.setenv("EIDOLON_MANIFEST_BATCH", "1")
        else:
            monkeypatch.delenv("EIDOLON_MANIFEST_BATCH", raising=False)
        config = default_config(root=tmp_path / label)
        controller = EpisodeController(config=config)
        task = _load_task(Path("examples/tasks/arith_01.json"))
        result = controller.run(task=task, mode=mode)
        return json.loads(result.ucr_path.read_text())

    payload_default = _run("default", batch=False)
    payload_batch = _run("batch", batch=True)

    assert set(payload_default.keys()) == set(payload_batch.keys())
    hashes_default = _lane_evidence_hashes(payload_default)
    hashes_batch = _lane_evidence_hashes(payload_batch)
    assert hashes_default
    assert hashes_batch
    assert set(hashes_default.keys()) == set(hashes_batch.keys())

    payloads_default = _lane_evidence_payloads(
        payload_default, tmp_path / "default" / "artifact_store"
    )
    payloads_batch = _lane_evidence_payloads(
        payload_batch, tmp_path / "batch" / "artifact_store"
    )
    assert set(payloads_default.keys()) == set(payloads_batch.keys())
    for lane, left in payloads_default.items():
        right = payloads_batch[lane]
        left = dict(left)
        right = dict(right)
        left.pop("duration_ms", None)
        right.pop("duration_ms", None)
        assert left == right

    breakdown = payload_batch.get("costs", {}).get("verify_breakdown_ms", {})
    assert isinstance(breakdown, dict)
    phase_ms = payload_batch.get("costs", {}).get("phase_ms", {})
    assert isinstance(phase_ms, dict)
    verify_ms = int(phase_ms.get("verify", 0))
    total_breakdown = sum(
        int(value) for value in breakdown.values() if isinstance(value, int)
    )
    assert abs(verify_ms - total_breakdown) <= 5
