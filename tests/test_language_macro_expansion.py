from eidolon_v16.bvps.ast import MacroCall, Program, Var
from eidolon_v16.bvps.interp import Interpreter
from eidolon_v16.language.apply import (
    expand_program,
    program_hash,
    program_pretty,
)
from eidolon_v16.language.spec import MacroTemplate


def _sample_macro_template() -> MacroTemplate:
    return MacroTemplate(
        params=["x"],
        body={
            "type": "binop",
            "op": "add",
            "left": {"type": "var", "name": "x"},
            "right": {"type": "int_const", "value": 1},
        },
    )


def _build_macro_program() -> Program:
    return Program(
        params=[("x", "Int")],
        body=MacroCall(name="incr", args=(Var("x"),)),
        return_type="Int",
    )


def test_macro_expansion_preserves_evaluation() -> None:
    macros = {"incr": _sample_macro_template()}
    program = _build_macro_program()
    expanded = expand_program(program, macros)
    interpreter = Interpreter(step_budget=100)
    value, _trace = interpreter.evaluate(expanded, {"x": 5})
    assert value == 6


def test_macro_expansion_deterministic_hashes() -> None:
    macros = {"incr": _sample_macro_template()}
    program = _build_macro_program()
    expanded_a = expand_program(program, macros)
    expanded_b = expand_program(program, macros)
    assert program_pretty(program) == "incr(x)"
    assert program_pretty(expanded_a) == "(x add 1)"
    assert program_hash(expanded_a) == program_hash(expanded_b)
    assert program_hash(program) != program_hash(expanded_a)
