from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidolon_v16.ucr.canonical import canonical_json_bytes, sha256_bytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LedgerEvent:
    seq: int
    ts: str
    event_type: str
    payload_json: str
    prev_hash: str
    event_hash: str


class Ledger:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                )
                """
            )

    def _latest_hash(self, conn: sqlite3.Connection) -> tuple[int, str]:
        query = "SELECT seq, event_hash FROM events ORDER BY seq DESC LIMIT 1"
        row = conn.execute(query).fetchone()
        if row is None:
            return 0, "0" * 64
        return int(row[0]), str(row[1])

    def append_event(self, event_type: str, payload: dict[str, Any]) -> LedgerEvent:
        payload_bytes = canonical_json_bytes(payload)
        payload_json = payload_bytes.decode("utf-8")
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self._connect() as conn:
            last_seq, prev_hash = self._latest_hash(conn)
            seq = last_seq + 1
            event_hash = sha256_bytes(
                prev_hash.encode("utf-8")
                + payload_bytes
                + event_type.encode("utf-8")
                + str(seq).encode("utf-8")
            )
            insert = (
                "INSERT INTO events (seq, ts, event_type, payload_json, prev_hash, event_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            )
            conn.execute(
                insert,
                (seq, ts, event_type, payload_json, prev_hash, event_hash),
            )
        logger.info("ledger append event seq=%s type=%s", seq, event_type)
        return LedgerEvent(
            seq=seq,
            ts=ts,
            event_type=event_type,
            payload_json=payload_json,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )

    def verify_chain(self) -> tuple[bool, str]:
        with self._connect() as conn:
            query = (
                "SELECT seq, event_type, payload_json, prev_hash, event_hash "
                "FROM events ORDER BY seq ASC"
            )
            rows = conn.execute(query).fetchall()
        prev_hash = "0" * 64
        expected_seq = 1
        for row in rows:
            seq, event_type, payload_json, stored_prev, stored_hash = row
            if seq != expected_seq:
                return False, f"sequence gap at {seq}"
            if stored_prev != prev_hash:
                return False, f"prev hash mismatch at {seq}"
            payload_bytes = payload_json.encode("utf-8")
            computed_hash = sha256_bytes(
                prev_hash.encode("utf-8")
                + payload_bytes
                + str(event_type).encode("utf-8")
                + str(seq).encode("utf-8")
            )
            if computed_hash != stored_hash:
                return False, f"hash mismatch at {seq}"
            prev_hash = stored_hash
            expected_seq += 1
        logger.info("ledger verify ok events=%s", len(rows))
        return True, "ok"
