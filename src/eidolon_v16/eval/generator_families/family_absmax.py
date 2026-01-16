from __future__ import annotations

import copy
import random
from typing import Any


class AbsMaxFamily:
    name = "absmax"
    canary_token = "CANARY-ABS-MAX-v0"

    def generate(self, base_spec: dict[str, Any], seed: int) -> list[dict[str, Any]]:
        return [
            self._tag(base_spec, f"{self.name}-base-{seed}"),
            self._tag(base_spec, f"{self.name}-alt-{seed + 1}"),
        ]

    def mutate(self, spec: dict[str, Any], seed: int) -> dict[str, Any]:
        rng = random.Random(seed)
        mutated = copy.deepcopy(spec)
        examples = list(mutated.get("examples", []))
        if examples:
            rng.shuffle(examples)
        mutated["examples"] = examples
        bounds = dict(mutated.get("bounds", {}))
        bounds["fuzz_trials"] = max(1, bounds.get("fuzz_trials", 3) - 1)
        mutated["bounds"] = bounds
        mutated["metadata"] = f"mutated-{seed}"
        return mutated

    def _tag(self, base_spec: dict[str, Any], label: str) -> dict[str, Any]:
        tagged = copy.deepcopy(base_spec)
        prompt = str(tagged.get("prompt", ""))
        tagged["prompt"] = f"{prompt} [{label}]".strip()
        tagged["family"] = self.name
        return tagged
