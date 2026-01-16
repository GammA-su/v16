from __future__ import annotations

from typing import Any


def canonicalize_number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise TypeError("bool is not a number")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            raise TypeError("empty string is not a number")
        try:
            parsed = float(raw)
        except ValueError as exc:
            raise TypeError("not a number") from exc
        return int(parsed) if parsed.is_integer() else parsed
    raise TypeError("not a number")
