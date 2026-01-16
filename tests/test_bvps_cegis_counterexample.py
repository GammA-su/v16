from __future__ import annotations

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import cegis as bvps_cegis
from eidolon_v16.bvps import types as bvps_types


def test_bvps_cegis_finds_counterexample() -> None:
    even_oracle = bvps_ast.BinOp(
        "eq",
        bvps_ast.BinOp("mod", bvps_ast.Var("x"), bvps_ast.IntConst(2)),
        bvps_ast.IntConst(0),
    ).to_dict()
    spec = bvps_types.spec_from_dict(
        {
            "name": "even",
            "inputs": [["x", "Int"]],
            "output": "Bool",
            "examples": [{"in": {"x": 2}, "out": True}],
            "bounds": {"max_depth": 3, "max_programs": 2000, "fuzz_trials": 5},
            "oracle": even_oracle,
        }
    )
    result = bvps_cegis.synthesize(spec, seed=42)
    assert result.stats.counterexamples >= 1
    checks = bvps_cegis.evaluate_examples(result.program, spec)
    assert all(item["ok"] for item in checks)
