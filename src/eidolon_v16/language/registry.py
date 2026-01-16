from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eidolon_v16.language.spec import PatchSpec


class PatchRecord(BaseModel):
    spec: PatchSpec
    bundle_dir: str


class LanguageRegistry(BaseModel):
    patches: list[PatchRecord] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> LanguageRegistry:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2))

    def register(self, spec: PatchSpec, bundle_dir: Path) -> None:
        bundle_path = str(bundle_dir)
        for record in self.patches:
            if record.spec.name == spec.name and record.spec.version == spec.version:
                record.bundle_dir = bundle_path
                return
        self.patches.append(PatchRecord(spec=spec, bundle_dir=bundle_path))

    def list_patches(self) -> list[PatchRecord]:
        return list(self.patches)

    def get_patch(self, name: str) -> PatchRecord | None:
        for record in self.patches:
            if record.spec.name == name:
                return record
        return None


def load_registry(path: Path) -> LanguageRegistry:
    return LanguageRegistry.load(path)


def save_registry(path: Path, registry: LanguageRegistry) -> None:
    registry.save(path)


def register_patch(path: Path, spec: PatchSpec, bundle_dir: Path) -> LanguageRegistry:
    registry = load_registry(path)
    registry.register(spec, bundle_dir)
    save_registry(path, registry)
    return registry


def list_patches(path: Path) -> list[PatchRecord]:
    registry = load_registry(path)
    return registry.list_patches()


def get_patch(path: Path, name: str) -> PatchRecord | None:
    registry = load_registry(path)
    return registry.get_patch(name)
