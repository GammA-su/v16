from __future__ import annotations

import threading
import time
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.json_canon import dumps_bytes
from eidolon_v16.ucr.canonical import sha256_canonical


@dataclass(frozen=True)
class BvpsPreloadStats:
    preload_ms: int
    entries: int
    errors: int


@dataclass
class BvpsPersistStats:
    enabled: bool = False
    persist_dir: str = ""
    lookups: int = 0
    reads: int = 0
    writes: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    errors: int = 0
    lookup_ns_sum: int = 0
    lookup_ns_max: int = 0
    read_ns_sum: int = 0
    read_ns_max: int = 0
    write_ns_sum: int = 0
    write_ns_max: int = 0
    preload_ns_sum: int = 0
    preload_ns_max: int = 0


_TOUCHED_PERSIST_DIRS: set[str] = set()
_TOUCHED_LOCK = threading.Lock()
_PERSIST_LOCK = threading.Lock()
_PERSIST_DIR: str | None = None
_PERSIST_STORE: ArtifactStore | None = None
_PERSIST_STATS = BvpsPersistStats()
_PERSIST_DISABLE_REASON = ""
_PERSIST_ENV_STATE: str | None = None


def persist_dir() -> str:
    override = os.getenv("EIDOLON_BVPS_PERSIST_DIR", "").strip()
    if override:
        return str(Path(override).expanduser().resolve())
    xdg_cache = os.getenv("XDG_CACHE_HOME", "").strip()
    if xdg_cache:
        base = Path(xdg_cache).expanduser()
    else:
        base = Path.home() / ".cache"
    return str((base / "eidolon_v16" / "bvps_persist").resolve())

def _current_env_state() -> str:
    return "|".join(
        [
            os.getenv("EIDOLON_BVPS_PERSIST", "").strip(),
            os.getenv("EIDOLON_BVPS_PERSIST_CACHE", "").strip(),
            os.getenv("EIDOLON_BVPS_PERSIST_DIR", "").strip(),
        ]
    )


def _parse_env_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    raw = value.strip().lower()
    if raw == "":
        return None
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _env_persist_enabled() -> tuple[bool, str]:
    primary = _parse_env_flag(os.getenv("EIDOLON_BVPS_PERSIST"))
    if primary is not None:
        return primary, "" if primary else "env_off"
    legacy = _parse_env_flag(os.getenv("EIDOLON_BVPS_PERSIST_CACHE"))
    if legacy is not None:
        return legacy, "" if legacy else "env_off"
    return True, ""


def _ensure_persist_initialized() -> None:
    global _PERSIST_DIR, _PERSIST_STORE, _PERSIST_STATS, _PERSIST_DISABLE_REASON, _PERSIST_ENV_STATE
    env_state = _current_env_state()
    with _PERSIST_LOCK:
        if _PERSIST_ENV_STATE != env_state:
            _PERSIST_ENV_STATE = env_state
            _PERSIST_DIR = None
            _PERSIST_STORE = None
            _PERSIST_STATS = BvpsPersistStats()
            _PERSIST_DISABLE_REASON = ""
        enabled, reason = _env_persist_enabled()
        if not enabled:
            _PERSIST_STATS.enabled = False
            _PERSIST_DISABLE_REASON = reason
            return
        dir_path = persist_dir()
        try:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        except OSError:
            _PERSIST_STATS.enabled = False
            _PERSIST_STATS.errors += 1
            _PERSIST_DISABLE_REASON = "mkdir_failed"
            return
        if _PERSIST_STORE is None or _PERSIST_DIR != dir_path:
            try:
                _PERSIST_DIR = dir_path
                _PERSIST_STORE = ArtifactStore(Path(dir_path))
            except Exception:
                _PERSIST_STATS.enabled = False
                _PERSIST_STATS.errors += 1
                _PERSIST_DISABLE_REASON = "init_failed"
                return
        _PERSIST_STATS.enabled = True
        _PERSIST_STATS.persist_dir = dir_path
        _PERSIST_DISABLE_REASON = ""


def persist_enabled() -> bool:
    _ensure_persist_initialized()
    return bool(_PERSIST_STATS.enabled)


def persist_disable_reason() -> str:
    _ensure_persist_initialized()
    return _PERSIST_DISABLE_REASON


def persist_store() -> ArtifactStore:
    _ensure_persist_initialized()
    if not _PERSIST_STATS.enabled or _PERSIST_STORE is None:
        raise RuntimeError("BVPS persist disabled")
    return _PERSIST_STORE


def persist_stats_snapshot() -> dict[str, Any]:
    _ensure_persist_initialized()
    with _PERSIST_LOCK:
        lookup_us_sum = int((_PERSIST_STATS.lookup_ns_sum + 999) // 1000)
        lookup_us_max = int((_PERSIST_STATS.lookup_ns_max + 999) // 1000)
        read_us_sum = int((_PERSIST_STATS.read_ns_sum + 999) // 1000)
        read_us_max = int((_PERSIST_STATS.read_ns_max + 999) // 1000)
        write_us_sum = int((_PERSIST_STATS.write_ns_sum + 999) // 1000)
        write_us_max = int((_PERSIST_STATS.write_ns_max + 999) // 1000)
        preload_us_sum = int((_PERSIST_STATS.preload_ns_sum + 999) // 1000)
        preload_us_max = int((_PERSIST_STATS.preload_ns_max + 999) // 1000)
        lookup_ms_sum = int(lookup_us_sum // 1000)
        lookup_ms_max = int(lookup_us_max // 1000)
        read_ms_sum = int(read_us_sum // 1000)
        read_ms_max = int(read_us_max // 1000)
        write_ms_sum = int(write_us_sum // 1000)
        write_ms_max = int(write_us_max // 1000)
        preload_ms_sum = int(preload_us_sum // 1000)
        preload_ms_max = int(preload_us_max // 1000)
        return {
            "bvps_persist_enabled": bool(_PERSIST_STATS.enabled),
            "bvps_persist_dir": _PERSIST_STATS.persist_dir,
            "bvps_persist_lookups": _PERSIST_STATS.lookups,
            "bvps_persist_reads": _PERSIST_STATS.reads,
            "bvps_persist_writes": _PERSIST_STATS.writes,
            "bvps_persist_bytes_read": _PERSIST_STATS.bytes_read,
            "bvps_persist_bytes_written": _PERSIST_STATS.bytes_written,
            "bvps_persist_errors": _PERSIST_STATS.errors,
            "bvps_persist_lookup_ns_sum": _PERSIST_STATS.lookup_ns_sum,
            "bvps_persist_lookup_ns_max": _PERSIST_STATS.lookup_ns_max,
            "bvps_persist_read_ns_sum": _PERSIST_STATS.read_ns_sum,
            "bvps_persist_read_ns_max": _PERSIST_STATS.read_ns_max,
            "bvps_persist_write_ns_sum": _PERSIST_STATS.write_ns_sum,
            "bvps_persist_write_ns_max": _PERSIST_STATS.write_ns_max,
            "bvps_persist_preload_ns_sum": _PERSIST_STATS.preload_ns_sum,
            "bvps_persist_preload_ns_max": _PERSIST_STATS.preload_ns_max,
            "bvps_persist_lookup_us_sum": lookup_us_sum,
            "bvps_persist_lookup_us_max": lookup_us_max,
            "bvps_persist_read_us_sum": read_us_sum,
            "bvps_persist_read_us_max": read_us_max,
            "bvps_persist_write_us_sum": write_us_sum,
            "bvps_persist_write_us_max": write_us_max,
            "bvps_persist_preload_us_sum": preload_us_sum,
            "bvps_persist_preload_us_max": preload_us_max,
            "bvps_persist_lookup_ms_sum": lookup_ms_sum,
            "bvps_persist_lookup_ms_max": lookup_ms_max,
            "bvps_persist_read_ms_sum": read_ms_sum,
            "bvps_persist_read_ms_max": read_ms_max,
            "bvps_persist_write_ms_sum": write_ms_sum,
            "bvps_persist_write_ms_max": write_ms_max,
            "bvps_persist_preload_ms": preload_ms_sum,
            "bvps_persist_preload_ms_max": preload_ms_max,
            "bvps_persist_disable_reason": _PERSIST_DISABLE_REASON,
        }


def reset_persist_stats() -> None:
    global _PERSIST_DISABLE_REASON, _PERSIST_DIR, _PERSIST_STORE, _PERSIST_ENV_STATE
    with _PERSIST_LOCK:
        _PERSIST_STATS.enabled = False
        _PERSIST_STATS.persist_dir = ""
        _PERSIST_STATS.lookups = 0
        _PERSIST_STATS.reads = 0
        _PERSIST_STATS.writes = 0
        _PERSIST_STATS.bytes_read = 0
        _PERSIST_STATS.bytes_written = 0
        _PERSIST_STATS.errors = 0
        _PERSIST_STATS.lookup_ns_sum = 0
        _PERSIST_STATS.lookup_ns_max = 0
        _PERSIST_STATS.read_ns_sum = 0
        _PERSIST_STATS.read_ns_max = 0
        _PERSIST_STATS.write_ns_sum = 0
        _PERSIST_STATS.write_ns_max = 0
        _PERSIST_STATS.preload_ns_sum = 0
        _PERSIST_STATS.preload_ns_max = 0
        _PERSIST_DISABLE_REASON = ""
        _PERSIST_DIR = None
        _PERSIST_STORE = None
        _PERSIST_ENV_STATE = None


def _record_lookup() -> None:
    with _PERSIST_LOCK:
        _PERSIST_STATS.lookups += 1


def record_persist_lookup() -> None:
    _record_lookup()


def record_persist_lookup_ms(ms: int) -> None:
    _record_lookup_ns(ms * 1_000_000)


def record_persist_lookup_us(us: int) -> None:
    _record_lookup_ns(us * 1000)


def _record_lookup_ns(ns: int) -> None:
    value = max(0, ns)
    with _PERSIST_LOCK:
        _PERSIST_STATS.lookup_ns_sum += value
        if value > _PERSIST_STATS.lookup_ns_max:
            _PERSIST_STATS.lookup_ns_max = value


def _record_read(size: int, ns: int) -> None:
    with _PERSIST_LOCK:
        _PERSIST_STATS.reads += 1
        _PERSIST_STATS.bytes_read += max(0, size)
        _PERSIST_STATS.read_ns_sum += max(0, ns)
        if ns > _PERSIST_STATS.read_ns_max:
            _PERSIST_STATS.read_ns_max = ns


def _record_write(size: int, ns: int) -> None:
    with _PERSIST_LOCK:
        _PERSIST_STATS.writes += 1
        _PERSIST_STATS.bytes_written += max(0, size)
        _PERSIST_STATS.write_ns_sum += max(0, ns)
        if ns > _PERSIST_STATS.write_ns_max:
            _PERSIST_STATS.write_ns_max = ns


def _record_error() -> None:
    with _PERSIST_LOCK:
        _PERSIST_STATS.errors += 1


def bvps_cache_key_string(spec_hash: str, macros_hash: str, attempt: int) -> str:
    return f"{spec_hash}:{macros_hash}:{attempt}"


def read_persistent_payload(store: ArtifactStore, content_hash: str) -> dict[str, Any]:
    try:
        start_ns = time.perf_counter_ns()
        data = store.read_bytes_by_hash(content_hash)
        ns = time.perf_counter_ns() - start_ns
        _record_read(len(data), max(0, ns))
        return json.loads(data.decode("utf-8"))
    except Exception:
        _record_error()
        raise


def iter_persistent_entries(store: ArtifactStore) -> list[Any]:
    manifest = store.load_manifest()
    entries = [entry for entry in manifest.entries if entry.type == "bvps_program_cache"]
    entries.sort(key=lambda entry: entry.hash)
    return entries


def parse_bvps_cache_payload(
    payload: dict[str, Any],
) -> tuple[tuple[str, str, int], str, dict[str, Any]] | None:
    spec_hash = str(payload.get("spec_hash", "")).strip()
    macros_hash = str(payload.get("macros_hash", "")).strip()
    if not spec_hash or not macros_hash:
        return None
    attempt = int(payload.get("attempt", 1))
    program = payload.get("program")
    if not isinstance(program, dict):
        return None
    expected_key = bvps_cache_key_string(spec_hash, macros_hash, attempt)
    payload_key = payload.get("cache_key")
    if payload_key is not None and str(payload_key) != expected_key:
        return None
    program_hash = payload.get("program_hash")
    computed_hash = sha256_canonical(program)
    if program_hash and str(program_hash) != computed_hash:
        return None
    record = {
        "program": program,
        "program_pretty": str(payload.get("program_pretty", "")),
        "report": dict(payload.get("report", {}))
        if isinstance(payload.get("report"), dict)
        else {},
        "solve_bvps_stats": dict(payload.get("solve_bvps_stats", {}))
        if isinstance(payload.get("solve_bvps_stats"), dict)
        else {},
        "macros_hash": macros_hash,
        "program_hash": computed_hash,
    }
    return (spec_hash, macros_hash, attempt), expected_key, record


def preload_persistent_cache(
    store: ArtifactStore,
) -> tuple[dict[tuple[str, str, int], dict[str, Any]], BvpsPreloadStats]:
    start = time.perf_counter()
    start_ns = time.perf_counter_ns()
    errors = 0
    cache: dict[tuple[str, str, int], dict[str, Any]] = {}
    for entry in iter_persistent_entries(store):
        payload = read_persistent_payload(store, entry.hash)
        parsed = parse_bvps_cache_payload(payload)
        if parsed is None:
            errors += 1
            continue
        key, _cache_key, record = parsed
        cache.setdefault(key, record)
    preload_ms = int((time.perf_counter() - start) * 1000)
    if preload_ms < 0:
        preload_ms = 0
    if preload_ms == 0 and cache:
        preload_ms = 1
    stats = BvpsPreloadStats(preload_ms=preload_ms, entries=len(cache), errors=errors)
    preload_ns_sum = time.perf_counter_ns() - start_ns
    if preload_ns_sum < 0:
        preload_ns_sum = 0
    with _PERSIST_LOCK:
        _PERSIST_STATS.preload_ns_sum += preload_ns_sum
        if preload_ns_sum > _PERSIST_STATS.preload_ns_max:
            _PERSIST_STATS.preload_ns_max = preload_ns_sum
    return cache, stats


def write_persistent_payload(
    store: ArtifactStore, payload: dict[str, Any], created_from: list[str]
) -> None:
    try:
        start_ns = time.perf_counter_ns()
        encoded = dumps_bytes(payload)
        encode_ns = time.perf_counter_ns() - start_ns
        if encode_ns < 0:
            encode_ns = 0
        write_start_ns = time.perf_counter_ns()
        store.put_json_bytes(
            payload,
            encoded,
            artifact_type="bvps_program_cache",
            producer="bvps",
            created_from=created_from,
        )
        write_ns = time.perf_counter_ns() - write_start_ns
        if write_ns < 0:
            write_ns = 0
        _record_write(len(encoded), encode_ns + write_ns)
    except Exception:
        _record_error()
        raise


def touch_persist_once(store: ArtifactStore) -> bool:
    persist_dir = str(store.root.resolve())
    with _TOUCHED_LOCK:
        if persist_dir in _TOUCHED_PERSIST_DIRS:
            return False
        _TOUCHED_PERSIST_DIRS.add(persist_dir)
    store.load_manifest()
    return True
