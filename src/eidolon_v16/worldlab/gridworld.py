from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eidolon_v16.worldlab.base import World


@dataclass
class GridWorld(World):
    width: int
    height: int
    goal: tuple[int, int]
    agent: tuple[int, int] = (0, 0)

    def reset(self, seed: int) -> dict[str, Any]:
        _ = seed
        self.agent = (0, 0)
        return self._obs()

    def step(self, action: str) -> tuple[dict[str, Any], int, bool, dict[str, Any]]:
        x, y = self.agent
        if action == "up":
            y = max(0, y - 1)
        elif action == "down":
            y = min(self.height - 1, y + 1)
        elif action == "left":
            x = max(0, x - 1)
        elif action == "right":
            x = min(self.width - 1, x + 1)
        self.agent = (x, y)
        done = self.agent == self.goal
        reward = 1 if done else 0
        info = {"agent": self.agent, "goal": self.goal}
        return self._obs(), reward, done, info

    def _obs(self) -> dict[str, Any]:
        return {"agent": self.agent, "goal": self.goal, "size": (self.width, self.height)}
