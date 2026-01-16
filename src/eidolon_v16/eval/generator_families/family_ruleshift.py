from __future__ import annotations

import copy
from typing import Any


class RuleShiftFamily:
    name = "ruleshift"
    canary_token = "CANARY-RULESHIFT-v0"

    def generate(
        self, base_spec: dict[str, Any], seed: int
    ) -> list[dict[str, Any]]:
        return [
            self._tag(base_spec, f"{self.name}-base-{seed}"),
            self._tag(base_spec, f"{self.name}-alt-{seed + 1}"),
        ]

    def mutate(self, spec: dict[str, Any], seed: int) -> dict[str, Any]:
        mutated = copy.deepcopy(spec)
        prompt = str(mutated.get("prompt", ""))
        mutated["prompt"] = f"{prompt} [shifted-{seed}]".strip()
        bounds = dict(mutated.get("bounds", {}))
        bounds["max_depth"] = bounds.get("max_depth", 3) + 1
        mutated["bounds"] = bounds
        mutated["metadata"] = f"ruleshift-mut-{seed}"
        return mutated

    def _tag(self, base_spec: dict[str, Any], label: str) -> dict[str, Any]:
        tagged = copy.deepcopy(base_spec)
        prompt = str(tagged.get("prompt", ""))
        tagged["prompt"] = f"{prompt} [{label}]".strip()
        tagged["family"] = self.name
        return tagged
