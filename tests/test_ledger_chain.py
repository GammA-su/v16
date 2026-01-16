from __future__ import annotations

import json
from pathlib import Path

from eidolon_v16.ledger.chain import append_event, verify_chain
from eidolon_v16.ucr.canonical import canonical_json_bytes


def test_ledger_chain_append_and_verify(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    append_event(ledger_path, "event", {"n": 1})
    append_event(ledger_path, "event", {"n": 2})
    append_event(ledger_path, "event", {"n": 3})
    ok, err = verify_chain(ledger_path)
    assert ok is True
    assert err is None

    lines = ledger_path.read_text().splitlines()
    corrupted = json.loads(lines[1])
    corrupted["payload"]["n"] = 999
    lines[1] = canonical_json_bytes(corrupted).decode("utf-8")
    ledger_path.write_text("\n".join(lines) + "\n")

    ok, err = verify_chain(ledger_path)
    assert ok is False
    assert err is not None
