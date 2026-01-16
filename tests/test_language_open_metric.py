from typing import Any

from eidolon_v16.language.admission import run_open_metric
from eidolon_v16.language.spec import MacroTemplate, PatchSpec


def _open_spec_payload() -> dict[str, Any]:
    return {
        "name": "incr",
        "inputs": [{"name": "x", "type": "Int"}],
        "output": "Int",
        "examples": [
            {"in": {"x": 0}, "out": 0},
            {"in": {"x": 1}, "out": 1},
        ],
        "bounds": {"max_depth": 3, "max_programs": 500},
        "target_body": {
            "type": "if",
            "cond": {
                "type": "binop",
                "op": "lt",
                "left": {"type": "var", "name": "x"},
                "right": {"type": "int_const", "value": 0},
            },
            "then": {
                "type": "binop",
                "op": "sub",
                "left": {"type": "var", "name": "x"},
                "right": {"type": "int_const", "value": 1},
            },
            "else": {
                "type": "binop",
                "op": "add",
                "left": {"type": "var", "name": "x"},
                "right": {"type": "int_const", "value": 1},
            },
        },
    }


def test_macro_patch_reduces_search_effort() -> None:
    spec_payload = _open_spec_payload()
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
        preconditions={"open_spec": spec_payload},
    )
    result = run_open_metric(spec, spec.macros, seed=0)
    assert result["status"] == "PASS"
    assert result["patched_cost"] < result["baseline_cost"]
