from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eidolon_v16.skills.types import SkillSpec


class SkillRegistry(BaseModel):
    skills: list[SkillSpec] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> SkillRegistry:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls.model_validate(data)
