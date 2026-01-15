from __future__ import annotations

import logging
from typing import Any

from eidolon_v16.worldlab.base import World

logger = logging.getLogger(__name__)


def run_rollout(world: World, actions: list[str], seed: int) -> dict[str, Any]:
    logger.info("worldlab rollout start steps=%s", len(actions))
    obs = world.reset(seed)
    steps = []
    done = False
    for action in actions:
        if done:
            break
        next_obs, reward, done, info = world.step(action)
        steps.append(
            {
                "action": action,
                "obs": obs,
                "next_obs": next_obs,
                "reward": reward,
                "done": done,
                "info": info,
            }
        )
        obs = next_obs
    logger.info("worldlab rollout complete done=%s", done)
    return {"steps": steps, "final_obs": obs, "done": done}
