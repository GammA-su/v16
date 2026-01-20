from __future__ import annotations

from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.json_canon import dumps_bytes


def test_put_json_bytes_hash_matches_put_json(tmp_path: Path) -> None:
    payload = {"b": [1, 2, 3], "a": {"x": 1, "y": 2}}
    store_legacy = ArtifactStore(tmp_path / "legacy")
    legacy_ref = store_legacy.put_json(payload, artifact_type="test", producer="unit")

    store_bytes = ArtifactStore(tmp_path / "bytes")
    encoded = dumps_bytes(payload)
    bytes_ref = store_bytes.put_json_bytes(
        payload,
        encoded,
        artifact_type="test",
        producer="unit",
    )

    assert legacy_ref.hash == bytes_ref.hash
