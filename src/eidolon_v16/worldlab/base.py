from __future__ import annotations

from typing import Any, Protocol


class World(Protocol):
    def reset(self, seed: int) -> dict[str, Any]:
        ...

    def step(self, action: str) -> tuple[dict[str, Any], int, bool, dict[str, Any]]:
        ...
