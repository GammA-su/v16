from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def canonical_json_str(obj: Any) -> str:
    return canonical_json_bytes(obj).decode("utf-8")


def canonical_model_bytes(model: BaseModel) -> bytes:
    data = model.model_dump(mode="json", by_alias=True)
    return canonical_json_bytes(data)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_canonical(obj: Any) -> str:
    return sha256_bytes(canonical_json_bytes(obj))


def compute_ucr_hash(ucr_payload: dict[str, Any]) -> str:
    payload = dict(ucr_payload)
    if "ucr_hash" in payload:
        payload["ucr_hash"] = ""
    hashes = dict(payload.get("hashes", {}))
    hashes["ucr_hash"] = ""
    payload["hashes"] = hashes
    return sha256_canonical(payload)
