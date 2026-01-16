from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import cegis as bvps_cegis
from eidolon_v16.bvps import enumerate as bvps_enumerate
from eidolon_v16.bvps.types import Spec, spec_from_dict
from eidolon_v16.eval.generator_families import get_generator_families
from eidolon_v16.language.apply import expand_program
from eidolon_v16.language.spec import MacroTemplate, PatchSpec
from eidolon_v16.ucr.canonical import canonical_json_bytes


@dataclass(frozen=True)
class AdmissionEvidence:
    open_metric: dict[str, Any]
    sealed_lite: dict[str, Any]


def run_open_metric(
    patch: PatchSpec,
    macros: dict[str, MacroTemplate],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    open_spec = patch.preconditions.get("open_spec")
    if not open_spec:
        return {"status": "SKIP", "reason": "missing open_spec"}
    target_body = open_spec.get("target_body")
    if not target_body:
        return {"status": "SKIP", "reason": "missing target_body"}
    spec = spec_from_dict(open_spec)
    target_expr = bvps_ast.expr_from_dict(target_body)
    target_hash = canonical_json_bytes(target_expr.to_dict())
    baseline_cost = _target_cost(
        spec,
        target_hash,
        macros={},
        max_programs=spec.bounds.max_programs,
    )
    patched_cost = _target_cost(
        spec,
        target_hash,
        macros=macros,
        max_programs=spec.bounds.max_programs,
    )
    status = "PASS" if patched_cost < baseline_cost else "FAIL"
    return {
        "status": status,
        "baseline_cost": baseline_cost,
        "patched_cost": patched_cost,
        "macros": list(macros.keys()),
    }


def _target_cost(
    spec: Spec,
    target_hash: bytes,
    *,
    macros: dict[str, MacroTemplate],
    max_programs: int,
) -> int:
    for idx, program in enumerate(
        bvps_enumerate.enumerate_programs(spec, macros=macros)
    ):
        if idx >= max_programs:
            break
        expanded = expand_program(program, macros)
        body_hash = canonical_json_bytes(expanded.body.to_dict())
        if body_hash == target_hash:
            return idx
    return max_programs


def run_sealed_lite_gate(
    patch: PatchSpec,
    macros: dict[str, MacroTemplate],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    preconditions = patch.preconditions
    base_spec_payload = preconditions.get("open_spec")
    if not base_spec_payload:
        return {"status": "SKIP", "reason": "missing open_spec"}
    spec = spec_from_dict(base_spec_payload)
    result = bvps_cegis.synthesize(spec, seed=seed, macros=macros)
    program = result.program
    families = get_generator_families()
    family_results: list[dict[str, Any]] = []
    sealed_cases: list[dict[str, Any]] = []
    overall_status = "PASS"
    for idx, family in enumerate(families):
        family_seed = seed + idx * 11
        variants = []
        for spec_payload in family.generate(base_spec_payload, family_seed):
            variants.append(spec_payload)
            variants.append(family.mutate(spec_payload, family_seed + 1))
        variant_reports = [_evaluate_variant(program, variant) for variant in variants]
        family_pass = all(report["pass"] for report in variant_reports)
        family_status = "PASS" if family_pass else "FAIL"
        if family_status == "FAIL":
            overall_status = "FAIL"
        family_results.append(
            {
                "family": family.name,
                "status": family_status,
                "variants": variant_reports,
            }
        )
        sealed_cases.extend(variant_reports)
    manual_specs = preconditions.get("sealed_specs", [])
    manual_reports = []
    for spec_payload in manual_specs:
        report = _evaluate_variant(program, spec_payload)
        manual_reports.append(report)
        if not report["pass"]:
            overall_status = "FAIL"
    sealed_cases.extend(manual_reports)
    return {
        "status": overall_status,
        "families": family_results,
        "sealed_cases": sealed_cases,
        "manual_specs": manual_reports,
        "canary_tokens": [family.canary_token for family in families],
    }


def _evaluate_variant(program: bvps_ast.Program, spec_payload: dict[str, Any]) -> dict[str, Any]:
    spec = spec_from_dict(spec_payload)
    checks = bvps_cegis.evaluate_examples(program, spec)
    passed = all(check.get("ok") for check in checks)
    return {"spec": spec_payload.get("name", "variant"), "pass": passed, "cases": checks}
