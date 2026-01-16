from __future__ import annotations

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps.interp import Interpreter


def test_bvps_interpreter_deterministic() -> None:
    program = bvps_ast.Program(
        params=[("x", "Int")],
        return_type="Int",
        body=bvps_ast.BinOp(
            op="add", left=bvps_ast.Var("x"), right=bvps_ast.IntConst(1)
        ),
    )
    interpreter = Interpreter(step_budget=20)
    out1, trace1 = interpreter.evaluate(program, {"x": 3}, trace=True)
    out2, trace2 = interpreter.evaluate(program, {"x": 3}, trace=True)

    assert out1 == out2 == 4
    assert trace1.steps == trace2.steps
    assert trace1.events == trace2.events
