from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eidolon_v16.worldlab.base import World


@dataclass
class GridWorld(World):
    width: int
    height: int
    goal: tuple[int, int]
    agent: tuple[int, int] = (0, 0)
    blocked: set[tuple[int, int]] = field(default_factory=set)

    def reset(self, seed: int) -> dict[str, Any]:
        _ = seed
        self.agent = (0, 0)
        return self._obs()

    def step(self, action: str) -> tuple[dict[str, Any], int, bool, dict[str, Any]]:
        x, y = self.agent
        invalid_action = None
        blocked_hit = False
        if action == "up":
            y = max(0, y - 1)
        elif action == "down":
            y = min(self.height - 1, y + 1)
        elif action == "left":
            x = max(0, x - 1)
        elif action == "right":
            x = min(self.width - 1, x + 1)
        else:
            invalid_action = action
        if invalid_action is not None:
            x, y = self.agent
        else:
            candidate = (x, y)
            if candidate in self.blocked:
                blocked_hit = True
                x, y = self.agent
        self.agent = (x, y)
        done = self.agent == self.goal
        reward = 1 if done else 0
        info = {"agent": self.agent, "goal": self.goal}
        if invalid_action is not None:
            info["invalid_action"] = invalid_action
        if blocked_hit:
            info["blocked"] = True
        return self._obs(), reward, done, info

    def _obs(self) -> dict[str, Any]:
        return {"agent": self.agent, "goal": self.goal, "size": (self.width, self.height)}
