from __future__ import annotations

from pathlib import Path

from eidolon_v16.ledger.db import Ledger


def test_ledger_append_and_verify(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    ledger.append_event("test", {"value": 1})
    ledger.append_event("test", {"value": 2})
    ok, message = ledger.verify_chain()
    assert ok, message
