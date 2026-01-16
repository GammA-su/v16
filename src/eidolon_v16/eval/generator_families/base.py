from __future__ import annotations

from typing import Any, Protocol


class GeneratorFamily(Protocol):
    name: str
    canary_token: str

    def generate(self, base_spec: dict[str, Any], seed: int) -> list[dict[str, Any]]:
        ...

    def mutate(self, spec: dict[str, Any], seed: int) -> dict[str, Any]:
        ...
