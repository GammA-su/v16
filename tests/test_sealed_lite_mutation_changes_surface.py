from __future__ import annotations

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.eval.generator_families.family_absmax import AbsMaxFamily


def test_sealed_lite_mutation_changes_surface() -> None:
    family = AbsMaxFamily()
    base_spec = {
        "name": "x_plus_one",
        "inputs": [["x", "Int"]],
        "output": "Int",
        "oracle": bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict(),
        "examples": [{"in": {"x": 2}, "out": 3}],
        "bounds": {"int_range": {"min": -3, "max": 3}},
    }
    spec = family.generate(base_spec, 0)[0]
    mutated = family.mutate(spec, 1)
    assert mutated["inputs"] == spec["inputs"]
    assert mutated.get("metadata")
