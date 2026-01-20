from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.ucr.canonical import canonical_json_bytes


def test_regress_vault_replay(tmp_path: Path) -> None:
    vault_dir = Path("tests/regress")
    entries = sorted(vault_dir.glob("*.json"))
    if not entries:
        pytest.skip("no regression vault entries")

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    store = ArtifactStore(config.paths.artifact_store)

    for entry in entries:
        payload = json.loads(entry.read_text())
        ucr_payload = payload.get("ucr")
        solution_record = payload.get("solution_artifact")
        assert isinstance(ucr_payload, dict)
        assert isinstance(solution_record, dict)

        solution_hash = str(solution_record.get("hash", ""))
        solution_payload = solution_record.get("payload")
        assert solution_hash
        assert isinstance(solution_payload, dict)

        ref = store.put_json(solution_payload, artifact_type="solution", producer="regress")
        assert ref.hash == solution_hash

        ucr_path = tmp_path / f"{entry.stem}_ucr.json"
        ucr_path.write_bytes(canonical_json_bytes(ucr_payload))
        assert controller.replay(ucr_path)
