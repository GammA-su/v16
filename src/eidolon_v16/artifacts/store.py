from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

from eidolon_v16.json_canon import dumps_bytes
from eidolon_v16.ucr.canonical import canonical_json_bytes, sha256_bytes, sha256_canonical


class ArtifactRef(BaseModel):
    hash: str
    type: str
    media_type: str
    size: int
    path: str | None = Field(default=None, exclude=True)


class ManifestEntry(BaseModel):
    hash: str
    type: str
    media_type: str
    producer: str
    created_from: list[str] = Field(default_factory=list)
    relpath: str | None = None
    size: int


class ArtifactManifest(BaseModel):
    entries: list[ManifestEntry] = Field(default_factory=list)

    def root_hash(self, exclude_types: set[str] | None = None) -> str:
        exclude_types = exclude_types or set()
        data = [
            entry.model_dump(mode="json", by_alias=True)
            for entry in self.entries
            if entry.type not in exclude_types
        ]
        return sha256_canonical(data)

    def add_entry(self, entry: ManifestEntry) -> None:
        if any(existing.hash == entry.hash for existing in self.entries):
            return
        self.entries.append(entry)
        self.entries.sort(key=lambda item: (item.hash, item.type))


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest_path = root / "manifest.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_cache: ArtifactManifest | None = None
        self._manifest_dirty = False
        self._manifest_batch = os.getenv("EIDOLON_MANIFEST_BATCH", "").strip() == "1"
        self._manifest_flush_mode = (
            os.getenv("EIDOLON_STORE_MANIFEST_FLUSH_MODE", "").strip() or "per_episode"
        )
        self._store_costs = {"hash_ms": 0, "blob_write_ms": 0, "manifest_ms": 0}
        self._manifest_detail = {
            "prepare_ms": 0,
            "hash_ms": 0,
            "serialize_ms": 0,
            "write_ms": 0,
            "fsync_ms": 0,
            "misc_ms": 0,
        }

    def store_costs_snapshot(self) -> dict[str, int]:
        return dict(self._store_costs)

    def store_costs_delta(self, start: dict[str, int]) -> dict[str, int]:
        return {
            key: max(0, self._store_costs.get(key, 0) - start.get(key, 0))
            for key in self._store_costs
        }

    def manifest_detail_snapshot(self) -> dict[str, int]:
        return dict(self._manifest_detail)

    def manifest_detail_delta(self, start: dict[str, int]) -> dict[str, int]:
        return {
            key: max(0, self._manifest_detail.get(key, 0) - start.get(key, 0))
            for key in self._manifest_detail
        }

    def set_manifest_flush_mode(self, mode: str) -> None:
        normalized = mode.strip().lower()
        if normalized not in {"per_episode", "per_suite"}:
            raise ValueError(f"invalid manifest flush mode: {mode}")
        self._manifest_flush_mode = normalized

    def manifest_flush_mode(self) -> str:
        return self._manifest_flush_mode

    def _record_cost(self, key: str, start: float) -> None:
        elapsed_ms = int(round((time.perf_counter() - start) * 1000))
        if elapsed_ms < 0:
            elapsed_ms = 0
        self._store_costs[key] = self._store_costs.get(key, 0) + elapsed_ms

    def _artifact_paths(self, content_hash: str) -> tuple[Path, Path]:
        subdir = self.root / "sha256" / content_hash[:2] / content_hash[2:4]
        subdir.mkdir(parents=True, exist_ok=True)
        data_path = subdir / f"{content_hash}.bin"
        meta_path = subdir / f"{content_hash}.meta.json"
        return data_path, meta_path

    def _relpath_for(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def load_manifest(self) -> ArtifactManifest:
        if self._manifest_cache is not None:
            return self._manifest_cache
        if not self.manifest_path.exists():
            self._manifest_cache = ArtifactManifest()
            return self._manifest_cache
        data = json.loads(self.manifest_path.read_text())
        for entry in data.get("entries", []):
            if "relpath" not in entry:
                legacy_path = entry.get("path")
                if legacy_path:
                    try:
                        entry["relpath"] = Path(legacy_path).relative_to(self.root).as_posix()
                    except ValueError:
                        entry["relpath"] = self._relpath_for(self._artifact_paths(entry["hash"])[0])
        manifest = ArtifactManifest.model_validate(data)
        self._manifest_cache = manifest
        return manifest

    def write_manifest(self, manifest: ArtifactManifest) -> None:
        start = time.perf_counter()
        detail_start_ns = time.monotonic_ns()
        prepare_start_ns = time.monotonic_ns()
        payload = manifest.model_dump(mode="json", by_alias=True)
        prepare_ms = int(round((time.monotonic_ns() - prepare_start_ns) / 1_000_000))
        if prepare_ms < 0:
            prepare_ms = 0
        hash_ms = 0
        serialize_start_ns = time.monotonic_ns()
        serialized = canonical_json_bytes(payload)
        serialize_ms = int(round((time.monotonic_ns() - serialize_start_ns) / 1_000_000))
        if serialize_ms < 0:
            serialize_ms = 0
        write_start_ns = time.monotonic_ns()
        self.manifest_path.write_bytes(serialized)
        write_ms = int(round((time.monotonic_ns() - write_start_ns) / 1_000_000))
        if write_ms < 0:
            write_ms = 0
        fsync_ms = 0
        total_ms = int(round((time.monotonic_ns() - detail_start_ns) / 1_000_000))
        if total_ms < 0:
            total_ms = 0
        misc_ms = total_ms - (prepare_ms + hash_ms + serialize_ms + write_ms + fsync_ms)
        if misc_ms < 0:
            misc_ms = 0
        self._manifest_detail["prepare_ms"] += prepare_ms
        self._manifest_detail["hash_ms"] += hash_ms
        self._manifest_detail["serialize_ms"] += serialize_ms
        self._manifest_detail["write_ms"] += write_ms
        self._manifest_detail["fsync_ms"] += fsync_ms
        self._manifest_detail["misc_ms"] += misc_ms
        self._record_cost("manifest_ms", start)
        self._manifest_dirty = False
        self._manifest_cache = manifest

    def flush_manifest(self, *, force: bool = False) -> dict[str, object]:
        if self._manifest_flush_mode == "per_suite" and not force:
            return {"total_ms": 0, "detail_ms": {}, "flush_count": 0}
        if self._manifest_cache is None:
            self._manifest_cache = self.load_manifest()
        if not self._manifest_dirty and not (
            force and self._manifest_cache.entries
        ):
            return {"total_ms": 0, "detail_ms": {}, "flush_count": 0}
        cost_start = self.store_costs_snapshot()
        detail_start = self.manifest_detail_snapshot()
        self.write_manifest(self._manifest_cache)
        cost_delta = self.store_costs_delta(cost_start)
        detail_delta = self.manifest_detail_delta(detail_start)
        total_ms = int(cost_delta.get("manifest_ms", 0))
        detail_ms = {
            "manifest_prepare_ms": int(detail_delta.get("prepare_ms", 0)),
            "manifest_hash_ms": int(detail_delta.get("hash_ms", 0)),
            "manifest_serialize_ms": int(detail_delta.get("serialize_ms", 0)),
            "manifest_write_ms": int(detail_delta.get("write_ms", 0)),
            "manifest_fsync_ms": int(detail_delta.get("fsync_ms", 0)),
            "manifest_misc_ms": int(detail_delta.get("misc_ms", 0)),
        }
        if total_ms == 0 and self._manifest_cache.entries:
            total_ms = 1
            if sum(detail_ms.values()) == 0:
                detail_ms["manifest_misc_ms"] = 1
        return {"total_ms": total_ms, "detail_ms": detail_ms, "flush_count": 1}

    def put_bytes(
        self,
        data: bytes,
        *,
        artifact_type: str,
        media_type: str,
        producer: str,
        created_from: list[str] | None = None,
    ) -> ArtifactRef:
        hash_start = time.perf_counter()
        content_hash = sha256_bytes(data)
        self._record_cost("hash_ms", hash_start)
        data_path, meta_path = self._artifact_paths(content_hash)
        write_start = time.perf_counter()
        if not data_path.exists():
            data_path.write_bytes(data)
        created_from = created_from or []
        relpath = self._relpath_for(data_path)
        metadata = {
            "hash": content_hash,
            "type": artifact_type,
            "media_type": media_type,
            "producer": producer,
            "created_from": created_from,
            "size": len(data),
            "relpath": relpath,
            "path": str(data_path),
        }
        meta_path.write_bytes(canonical_json_bytes(metadata))
        self._record_cost("blob_write_ms", write_start)

        manifest = self.load_manifest()
        entry = ManifestEntry(
            hash=content_hash,
            type=artifact_type,
            media_type=media_type,
            producer=producer,
            created_from=created_from,
            size=len(data),
            relpath=relpath,
        )
        manifest.add_entry(entry)
        if self._manifest_batch or self._manifest_flush_mode == "per_suite":
            self._manifest_dirty = True
            self._manifest_cache = manifest
        else:
            self.write_manifest(manifest)

        return ArtifactRef(
            hash=content_hash,
            type=artifact_type,
            media_type=media_type,
            size=len(data),
        )

    def put_json(
        self,
        payload: Any,
        *,
        artifact_type: str,
        producer: str,
        created_from: list[str] | None = None,
    ) -> ArtifactRef:
        data = dumps_bytes(payload)
        return self.put_json_bytes(
            payload,
            data,
            artifact_type=artifact_type,
            media_type="application/json",
            producer=producer,
            created_from=created_from,
        )

    def put_json_bytes(
        self,
        payload: Any,
        encoded: bytes,
        *,
        artifact_type: str,
        producer: str,
        created_from: list[str] | None = None,
        media_type: str = "application/json",
    ) -> ArtifactRef:
        _ = payload
        return self.put_bytes(
            encoded,
            artifact_type=artifact_type,
            media_type=media_type,
            producer=producer,
            created_from=created_from,
        )

    def resolve_paths_by_hash(self, content_hash: str) -> tuple[Path, Path]:
        return self._artifact_paths(content_hash)

    def resolve_data_path(self, content_hash: str) -> Path:
        data_path, _meta_path = self._artifact_paths(content_hash)
        return data_path

    def get_by_hash(self, content_hash: str) -> tuple[bytes, dict[str, Any]]:
        data_path, meta_path = self.resolve_paths_by_hash(content_hash)
        data = data_path.read_bytes()
        meta = json.loads(meta_path.read_text())
        return data, meta

    def read_bytes_by_hash(self, content_hash: str) -> bytes:
        data_path = self.resolve_data_path(content_hash)
        return data_path.read_bytes()

    def read_json_by_hash(self, content_hash: str) -> dict[str, Any]:
        data = self.read_bytes_by_hash(content_hash)
        return cast(dict[str, Any], json.loads(data.decode("utf-8")))

    def path_for_hash(self, content_hash: str) -> Path:
        data_path, _meta_path = self.resolve_paths_by_hash(content_hash)
        return data_path

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        data_path, _meta_path = self._artifact_paths(ref.hash)
        return data_path.read_bytes()
