from __future__ import annotations

from eidolon_v16.ucr.canonical import canonical_json_bytes, compute_ucr_hash, sha256_canonical


def test_canonical_json_stability() -> None:
    obj1 = {"b": 1, "a": 2}
    obj2 = {"a": 2, "b": 1}
    assert canonical_json_bytes(obj1) == canonical_json_bytes(obj2)
    assert sha256_canonical(obj1) == sha256_canonical(obj2)


def test_compute_ucr_hash_stable() -> None:
    payload = {
        "episode_id": "ep-1",
        "hashes": {"ucr_hash": "", "artifact_manifest_hash": "abc"},
        "task_input": {"raw": {}, "normalized": {}},
    }
    first = compute_ucr_hash(payload)
    second = compute_ucr_hash(payload)
    assert first == second
