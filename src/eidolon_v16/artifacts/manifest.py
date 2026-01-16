from __future__ import annotations

from pathlib import Path
from typing import Any

from eidolon_v16.ucr.canonical import sha256_bytes


def build_artifact_manifest(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not root.exists():
        return entries
    files = [path for path in root.rglob("*") if path.is_file()]
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relpath = path.relative_to(root).as_posix()
        data = path.read_bytes()
        entries.append(
            {
                "path": relpath,
                "sha256": sha256_bytes(data),
                "bytes": len(data),
            }
        )
    return entries
