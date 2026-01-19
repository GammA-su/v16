from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from eidolon_v16.artifacts.store import ArtifactRef, ArtifactStore
from eidolon_v16.skills.spec import SkillSpec
from eidolon_v16.ucr.canonical import sha256_canonical


@dataclass
class SkillBundle:
    spec: SkillSpec
    program: dict[str, Any]
    tests: dict[str, Any]
    verify_profile: dict[str, Any]
    artifact_refs: list[ArtifactRef]
    bundle_name: str


def write_skill_bundle(
    *,
    store: ArtifactStore,
    skill_spec: SkillSpec,
    program_ast: dict[str, Any],
    tests: dict[str, Any],
    verify_profile: dict[str, Any],
) -> SkillBundle:
    bundle_name = skill_spec.name
    artifacts = [
        f"skills/{bundle_name}/skill.json",
        f"skills/{bundle_name}/program.json",
        f"skills/{bundle_name}/tests.json",
        f"skills/{bundle_name}/verify_profile.json",
    ]
    spec_payload = skill_spec.model_dump(mode="json")
    spec_payload["artifacts"] = artifacts
    updated_spec = SkillSpec.model_validate(spec_payload)

    spec_ref = store.put_json(
        updated_spec.model_dump(mode="json"),
        artifact_type=f"skill_spec:{bundle_name}",
        producer="skills",
    )
    program_ref = store.put_json(
        program_ast,
        artifact_type=f"skill_program:{bundle_name}",
        producer="skills",
        created_from=[spec_ref.hash],
    )
    tests_ref = store.put_json(
        tests,
        artifact_type=f"skill_tests:{bundle_name}",
        producer="skills",
        created_from=[spec_ref.hash],
    )
    verify_ref = store.put_json(
        verify_profile,
        artifact_type=f"skill_verify_profile:{bundle_name}",
        producer="skills",
        created_from=[spec_ref.hash],
    )
    return SkillBundle(
        spec=updated_spec,
        program=program_ast,
        tests=tests,
        verify_profile=verify_profile,
        artifact_refs=[spec_ref, program_ref, tests_ref, verify_ref],
        bundle_name=bundle_name,
    )


def read_skill_bundle(bundle_dir: Path) -> SkillBundle:
    spec_path = bundle_dir / "skill.json"
    program_path = bundle_dir / "program.json"
    tests_path = bundle_dir / "tests.json"
    verify_path = bundle_dir / "verify_profile.json"
    spec = SkillSpec.model_validate_json(spec_path.read_text())
    program = program_path.read_text()
    tests = tests_path.read_text()
    verify_profile = verify_path.read_text()
    return SkillBundle(
        spec=spec,
        program=_load_json(program),
        tests=_load_json(tests),
        verify_profile=_load_json(verify_profile),
        artifact_refs=[],
        bundle_name=spec.name,
    )


def bundle_identity(bundle: SkillBundle) -> dict[str, str]:
    spec_payload = bundle.spec.model_dump(mode="json")
    spec_hash = sha256_canonical(spec_payload)
    bundle_payload = {
        "spec": spec_payload,
        "program": bundle.program,
        "tests": bundle.tests,
        "verify_profile": bundle.verify_profile,
    }
    bundle_hash = sha256_canonical(bundle_payload)
    return {
        "name": bundle.spec.name,
        "version": bundle.spec.version,
        "spec_hash": spec_hash,
        "bundle_hash": bundle_hash,
    }


def _load_json(raw: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(raw))
