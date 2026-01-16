from __future__ import annotations

import json
from typing import Any

from eidolon_v16.ucr.canonical import canonical_json_bytes, compute_ucr_hash


def test_ucr_hash_roundtrip_stable() -> None:
    payload: dict[str, Any] = {
        "schema_version": "ucr/v1",
        "episode_id": "ep-test",
        "ts_utc": "2025-01-01T00:00:00Z",
        "task_text": "Compute 1 + 1",
        "interpretations": [],
        "chosen_interpretation_id": None,
        "budgets": {"steps": 0, "cpu_ms": 0},
        "kernel": {"kind": "stub"},
        "solution": {"solution_kind": "arith_eval", "output": 2},
        "lane_verdicts": {},
        "costs": {},
        "artifact_manifest": [
            {"path": "solution.json", "sha256": "0" * 64, "bytes": 12}
        ],
        "task_input": {"raw": {}, "normalized": {}},
        "decision": {"action": "answer", "rationale": "ok", "assumptions": []},
        "solution_artifacts": [],
        "verification": [],
        "final_result": "result=2",
        "hashes": {"ucr_hash": "", "artifact_manifest_hash": ""},
        "ucr_hash": "",
        "witness_packet": {"hash": "", "type": "witness_packet", "media_type": "", "size": 0},
    }
    first_bytes = canonical_json_bytes(payload)
    parsed = json.loads(first_bytes.decode("utf-8"))
    second_bytes = canonical_json_bytes(parsed)
    assert first_bytes == second_bytes
    assert compute_ucr_hash(payload) == compute_ucr_hash(parsed)
