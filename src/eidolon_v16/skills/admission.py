from __future__ import annotations

from dataclasses import dataclass

from eidolon_v16.skills.types import SkillSpec


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    rationale: str


def run_admission(skill: SkillSpec) -> AdmissionResult:
    if not skill.triggers:
        return AdmissionResult(admitted=False, rationale="missing triggers")
    if not skill.verifiers:
        return AdmissionResult(admitted=False, rationale="missing verifiers")
    return AdmissionResult(admitted=False, rationale="admission disabled in MVP")
