from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from eidolon_v16.skills.bundle import SkillBundle
from eidolon_v16.ucr.canonical import canonical_json_bytes


def ensure_skills_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_bundle(bundle: SkillBundle, skills_dir: Path) -> Path:
    skills_dir = ensure_skills_dir(skills_dir)
    bundle_root = skills_dir / bundle.spec.name / bundle.spec.version
    bundle_root.mkdir(parents=True, exist_ok=True)
    _write_json(bundle_root / "skill.json", bundle.spec.model_dump(mode="json"))
    _write_json(bundle_root / "program.json", bundle.program)
    _write_json(bundle_root / "tests.json", bundle.tests)
    _write_json(bundle_root / "verify_profile.json", bundle.verify_profile)
    return bundle_root


def load_bundle(bundle_dir: Path) -> SkillBundle:
    from eidolon_v16.skills.bundle import read_skill_bundle

    return read_skill_bundle(bundle_dir)


def copy_bundle(bundle_dir: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / bundle_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(bundle_dir, dest)
    return dest


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(canonical_json_bytes(payload))
