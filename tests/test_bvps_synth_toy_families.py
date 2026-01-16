from __future__ import annotations

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import cegis as bvps_cegis
from eidolon_v16.bvps import types as bvps_types


def test_bvps_synth_x_plus_one() -> None:
    oracle = bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict()
    spec = bvps_types.spec_from_dict(
        {
            "name": "x_plus_one",
            "inputs": [["x", "Int"]],
            "output": "Int",
            "examples": [{"in": {"x": 2}, "out": 3}],
            "bounds": {"max_depth": 2, "max_programs": 500, "fuzz_trials": 10},
            "oracle": oracle,
        }
    )
    result = bvps_cegis.synthesize(spec, seed=0)
    checks = bvps_cegis.evaluate_examples(result.program, spec)
    assert all(item["ok"] for item in checks)


def test_bvps_synth_max2() -> None:
    oracle = bvps_ast.IfThenElse(
        bvps_ast.BinOp("gt", bvps_ast.Var("x"), bvps_ast.Var("y")),
        bvps_ast.Var("x"),
        bvps_ast.Var("y"),
    ).to_dict()
    spec = bvps_types.spec_from_dict(
        {
            "name": "max2",
            "inputs": [["x", "Int"], ["y", "Int"]],
            "output": "Int",
            "examples": [{"in": {"x": 1, "y": 2}, "out": 2}],
            "bounds": {"max_depth": 3, "max_programs": 2000, "fuzz_trials": 10},
            "oracle": oracle,
        }
    )
    result = bvps_cegis.synthesize(spec, seed=1)
    checks = bvps_cegis.evaluate_examples(result.program, spec)
    assert all(item["ok"] for item in checks)


def test_bvps_synth_abs_even() -> None:
    abs_oracle = bvps_ast.IfThenElse(
        bvps_ast.BinOp("lt", bvps_ast.Var("x"), bvps_ast.IntConst(0)),
        bvps_ast.BinOp("sub", bvps_ast.IntConst(0), bvps_ast.Var("x")),
        bvps_ast.Var("x"),
    ).to_dict()
    abs_spec = bvps_types.spec_from_dict(
        {
            "name": "abs",
            "inputs": [["x", "Int"]],
            "output": "Int",
            "examples": [{"in": {"x": -2}, "out": 2}],
            "bounds": {"max_depth": 3, "max_programs": 3000, "fuzz_trials": 10},
            "oracle": abs_oracle,
        }
    )
    abs_result = bvps_cegis.synthesize(abs_spec, seed=2)
    abs_checks = bvps_cegis.evaluate_examples(abs_result.program, abs_spec)
    assert all(item["ok"] for item in abs_checks)

    even_oracle = bvps_ast.BinOp(
        "eq",
        bvps_ast.BinOp("mod", bvps_ast.Var("x"), bvps_ast.IntConst(2)),
        bvps_ast.IntConst(0),
    ).to_dict()
    even_spec = bvps_types.spec_from_dict(
        {
            "name": "even",
            "inputs": [["x", "Int"]],
            "output": "Bool",
            "examples": [{"in": {"x": 2}, "out": True}],
            "bounds": {"max_depth": 3, "max_programs": 3000, "fuzz_trials": 10},
            "oracle": even_oracle,
        }
    )
    even_result = bvps_cegis.synthesize(even_spec, seed=3)
    even_checks = bvps_cegis.evaluate_examples(even_result.program, even_spec)
    assert all(item["ok"] for item in even_checks)
