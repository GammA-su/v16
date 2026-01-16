from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eidolon_v16.language.spec import PatchSpec
from eidolon_v16.ucr.canonical import canonical_json_bytes


def ensure_language_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_patch_bundle(spec: PatchSpec, language_dir: Path) -> Path:
    language_dir = ensure_language_dir(language_dir)
    bundle_root = language_dir / spec.name / spec.version
    bundle_root.mkdir(parents=True, exist_ok=True)
    _write_json(bundle_root / "patch.json", spec.model_dump(mode="json"))
    return bundle_root


def read_patch_bundle(bundle_dir: Path) -> PatchSpec:
    path = bundle_dir / "patch.json"
    data = json.loads(path.read_text())
    return PatchSpec.model_validate(data)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(canonical_json_bytes(payload))
