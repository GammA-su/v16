from __future__ import annotations

import copy
from typing import Any


class ListsFamily:
    name = "lists"
    canary_token = "CANARY-LISTS-v0"

    def generate(
        self, base_spec: dict[str, Any], seed: int
    ) -> list[dict[str, Any]]:
        return [
            self._tag(base_spec, f"{self.name}-base-{seed}"),
            self._tag(base_spec, f"{self.name}-alt-{seed + 1}"),
        ]

    def mutate(self, spec: dict[str, Any], seed: int) -> dict[str, Any]:
        mutated = copy.deepcopy(spec)
        bounds = dict(mutated.get("bounds", {}))
        bounds["int_range"] = {
            "min": bounds.get("int_range", {}).get("min", -3) - 1,
            "max": bounds.get("int_range", {}).get("max", 3) + 1,
        }
        mutated["bounds"] = bounds
        examples = list(mutated.get("examples", []))
        if examples:
            examples.append(examples.pop(0))
        mutated["examples"] = examples
        mutated["metadata"] = f"list-mut-{seed}"
        return mutated

    def _tag(self, base_spec: dict[str, Any], label: str) -> dict[str, Any]:
        tagged = copy.deepcopy(base_spec)
        prompt = str(tagged.get("prompt", ""))
        tagged["prompt"] = f"{prompt} [{label}]".strip()
        tagged["family"] = self.name
        return tagged
