from __future__ import annotations

import pytest

from eidolon_v16.arith_types import canonicalize_number


@pytest.mark.parametrize(
    "value, expected",
    [
        (14, 14),
        (14.0, 14),
        (14.5, 14.5),
        ("14", 14),
        (" 14 ", 14),
        ("14.0", 14),
        ("14.5", 14.5),
        (" 14.5 ", 14.5),
        ("+3", 3),
        ("-2.0", -2),
    ],
)
def test_canonicalize_number_valid(value: object, expected: float | int) -> None:
    assert canonicalize_number(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        "",
        "  ",
        "nope",
        "fourteen",
        None,
        [],
        {},
    ],
)
def test_canonicalize_number_invalid(value: object) -> None:
    with pytest.raises(TypeError):
        canonicalize_number(value)
