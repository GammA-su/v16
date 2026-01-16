from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidolon_v16.ucr.canonical import canonical_json_bytes, sha256_bytes


def append_event(ledger_path: Path, kind: str, payload: dict[str, Any]) -> str:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    prev_hash = _read_last_hash(ledger_path)
    ts_utc = _utc_now()
    event = {
        "ts_utc": ts_utc,
        "kind": kind,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    event_hash = _compute_event_hash(event)
    event["event_hash"] = event_hash
    line = canonical_json_bytes(event).decode("utf-8")
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return event_hash


def verify_chain(ledger_path: Path) -> tuple[bool, str | None]:
    if not ledger_path.exists():
        return True, None
    prev_hash = "0" * 64
    with ledger_path.open("r", encoding="utf-8") as handle:
        for idx, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                return False, f"invalid json at line {idx}: {exc}"
            stored_prev = str(event.get("prev_hash", ""))
            stored_hash = str(event.get("event_hash", ""))
            if stored_prev != prev_hash:
                return False, f"prev hash mismatch at line {idx}"
            recomputed = _compute_event_hash(event)
            if recomputed != stored_hash:
                return False, f"hash mismatch at line {idx}"
            prev_hash = stored_hash
    return True, None


def _compute_event_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload["event_hash"] = ""
    return sha256_bytes(canonical_json_bytes(payload))


def _read_last_hash(ledger_path: Path) -> str:
    if not ledger_path.exists():
        return "0" * 64
    with ledger_path.open("rb") as handle:
        handle.seek(0, 2)
        end = handle.tell()
        if end == 0:
            return "0" * 64
        offset = min(end, 4096)
        handle.seek(-offset, 2)
        chunk = handle.read().splitlines()
        if not chunk:
            return "0" * 64
        last_line = chunk[-1].decode("utf-8").strip()
        if not last_line:
            return "0" * 64
        event = json.loads(last_line)
        return str(event.get("event_hash", "0" * 64))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
