from typing import Any

from eidolon_v16.language.admission import run_sealed_lite_gate
from eidolon_v16.language.spec import MacroTemplate, PatchSpec


def _sealed_payload() -> dict[str, Any]:
    return {
        "name": "incr",
        "inputs": [{"name": "x", "type": "Int"}],
        "output": "Int",
        "examples": [
            {"in": {"x": 0}, "out": 0},
            {"in": {"x": 1}, "out": 1},
        ],
        "bounds": {"max_depth": 2, "max_programs": 50},
        "target_body": {
            "type": "binop",
            "op": "add",
            "left": {"type": "var", "name": "x"},
            "right": {"type": "int_const", "value": 1},
        },
    }


def _failed_variant() -> dict[str, Any]:
    return {
        "name": "incr-variant",
        "inputs": [{"name": "x", "type": "Int"}],
        "output": "Int",
        "examples": [
            {"in": {"x": 0}, "out": 2},
            {"in": {"x": 1}, "out": 3},
        ],
        "bounds": {"max_depth": 2, "max_programs": 20},
    }


def test_language_patch_rejected_on_sealed_regression() -> None:
    spec_payload = _sealed_payload()
    spec = PatchSpec(
        name="macro-incr",
        version="0.1",
        created_ts_utc="2024-01-01T00:00:00Z",
        scope="incr",
        macros={
            "incr": MacroTemplate(
                params=["x"],
                param_types=["Int"],
                return_type="Int",
                body=spec_payload["target_body"],
            )
        },
        preconditions={
            "open_spec": spec_payload,
            "sealed_specs": [_failed_variant()],
        },
    )
    result = run_sealed_lite_gate(spec, spec.macros, seed=0)
    assert result["status"] == "FAIL"
    assert any(not case["pass"] for case in result["manual_specs"])
