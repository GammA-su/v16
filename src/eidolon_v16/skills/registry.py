from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eidolon_v16.skills.spec import SkillSpec


class SkillRecord(BaseModel):
    spec: SkillSpec
    bundle_dir: str


class SkillRegistry(BaseModel):
    skills: list[SkillRecord] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> SkillRegistry:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2))

    def register(self, spec: SkillSpec, bundle_dir: Path) -> None:
        bundle_path = str(bundle_dir)
        for record in self.skills:
            if record.spec.name == spec.name and record.spec.version == spec.version:
                record.bundle_dir = bundle_path
                return
        self.skills.append(SkillRecord(spec=spec, bundle_dir=bundle_path))

    def list_skills(self) -> list[SkillRecord]:
        return list(self.skills)

    def get_skill(self, name: str) -> SkillRecord | None:
        for record in self.skills:
            if record.spec.name == name:
                return record
        return None


def load_registry(path: Path) -> SkillRegistry:
    return SkillRegistry.load(path)


def save_registry(path: Path, registry: SkillRegistry) -> None:
    registry.save(path)


def register_skill(path: Path, spec: SkillSpec, bundle_dir: Path) -> SkillRegistry:
    registry = load_registry(path)
    registry.register(spec, bundle_dir)
    save_registry(path, registry)
    return registry


def list_skills(path: Path) -> list[SkillRecord]:
    registry = load_registry(path)
    return registry.list_skills()


def get_skill(path: Path, name: str) -> SkillRecord | None:
    registry = load_registry(path)
    return registry.get_skill(name)
