from __future__ import annotations

import pytest

from eidolon_v16.utils import safe_eval_arith


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("-3 + 5", 2),
        ("+3", 3),
        ("5 / 2", 2.5),
        ("7 // 2", 3),
        ("7 % 4", 3),
        ("2 ** 3", 8),
        ("2.5 + 0.5", 3.0),
    ],
)
def test_safe_eval_arith_valid(expr: str, expected: float | int) -> None:
    assert safe_eval_arith(expr) == expected


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo nope')",
        "open('file')",
        "a + 1",
        "(1).real",
        "x[0]",
        "[1, 2, 3]",
        "(lambda x: x)(1)",
        "True",
    ],
)
def test_safe_eval_arith_rejects(expr: str) -> None:
    with pytest.raises(ValueError):
        safe_eval_arith(expr)
