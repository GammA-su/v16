from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.manifest import build_artifact_manifest
from eidolon_v16.config import default_config
from eidolon_v16.ledger.chain import verify_chain
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.canonical import compute_ucr_hash
from eidolon_v16.ucr.models import TaskInput


def test_truth_spine_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "arith-truth",
            "kind": "arith",
            "prompt": "Compute 2 + 3 * 4",
            "data": {"expression": "2 + 3 * 4"},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    run_dir = config.paths.runs_dir / result.ucr_path.parent.name
    ucr_path = run_dir / "ucr.json"
    witness_path = run_dir / "witness.json"
    assert ucr_path.exists()
    assert witness_path.exists()

    payload = json.loads(ucr_path.read_text())
    assert payload["hashes"]["ucr_hash"] == compute_ucr_hash(payload)

    manifest = payload.get("artifact_manifest", [])
    assert manifest
    for entry in manifest:
        assert "path" in entry
        assert "sha256" in entry
        assert len(entry["sha256"]) == 64
        assert entry.get("bytes", 0) > 0

    ok, err = verify_chain(config.paths.ledger_chain)
    assert ok is True
    assert err is None

    artifacts_dir = run_dir / "artifacts"
    assert build_artifact_manifest(artifacts_dir) == manifest
