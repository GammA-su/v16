from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

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
        payload = manifest.model_dump(mode="json", by_alias=True)
        self.manifest_path.write_bytes(canonical_json_bytes(payload))
        self._manifest_dirty = False
        self._manifest_cache = manifest

    def flush_manifest(self) -> None:
        if not self._manifest_dirty or self._manifest_cache is None:
            return
        self.write_manifest(self._manifest_cache)

    def put_bytes(
        self,
        data: bytes,
        *,
        artifact_type: str,
        media_type: str,
        producer: str,
        created_from: list[str] | None = None,
    ) -> ArtifactRef:
        content_hash = sha256_bytes(data)
        data_path, meta_path = self._artifact_paths(content_hash)
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
        if self._manifest_batch:
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
        data = canonical_json_bytes(payload)
        return self.put_bytes(
            data,
            artifact_type=artifact_type,
            media_type="application/json",
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
