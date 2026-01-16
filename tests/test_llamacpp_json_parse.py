from __future__ import annotations

import pytest

from eidolon_v16.kernels.llamacpp_kernel import _safe_json_loads


@pytest.mark.parametrize(
    "payload",
    [
        '{"a": 1}\n',
        '{"a": 1}\n\n',
        '{"a": 1}\nEXTRA',
        'noise\n{"a": 1}\n',
    ],
)
def test_safe_json_loads(payload: str) -> None:
    assert _safe_json_loads(payload) == {"a": 1}
