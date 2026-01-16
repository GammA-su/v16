from __future__ import annotations

import random

from eidolon_v16.bvps.interpreter import Interpreter
from eidolon_v16.bvps.synth import synthesize_program
from eidolon_v16.kernel.base import Kernel, SolutionCandidate
from eidolon_v16.ucr.models import AmbiguitySlot, Interpretation, TaskInput
from eidolon_v16.utils import safe_eval_arith
from eidolon_v16.worldlab.gridworld import GridWorld


class StubKernel(Kernel):
    def propose_interpretations(self, task: TaskInput, *, seed: int) -> list[Interpretation]:
        rng = random.Random(seed)
        normalized = task.normalized
        prompt = normalized.get("prompt", "")
        kind = normalized.get("kind", "unknown")
        ambiguity = AmbiguitySlot(
            slot_id="scope",
            description="Assume literal reading of the prompt.",
            values=["literal", "fallback"],
        )
        interpretations = [
            Interpretation(
                interpretation_id=f"{kind}-literal",
                description=f"Literal interpretation of: {prompt}",
                ambiguity_slots=[ambiguity],
            ),
            Interpretation(
                interpretation_id=f"{kind}-fallback",
                description=f"Fallback structured interpretation for kind={kind}.",
                assumptions=["Use provided data fields when prompt is underspecified."],
            ),
        ]
        rng.shuffle(interpretations)
        return interpretations

    def propose_solution(
        self, task: TaskInput, interpretation: Interpretation, *, seed: int
    ) -> SolutionCandidate:
        normalized = task.normalized
        kind = normalized.get("kind", "unknown")
        data = normalized.get("data", {})
        if kind == "arith":
            expr = str(data.get("expression", "0"))
            value = safe_eval_arith(expr)
            return SolutionCandidate(output=value, solution_kind="arith_result")
        if kind == "list":
            result = synthesize_program(task=task, seed=seed)
            interpreter = Interpreter(step_limit=2000)
            output, trace = interpreter.run(result.program, [result.input_list])
            return SolutionCandidate(
                output=output,
                solution_kind="bvps_program",
                program=result.program.to_dict(),
                trace=trace,
            )
        if kind == "world":
            world = GridWorld(width=3, height=3, goal=(2, 2))
            actions = _plan_world_actions(world)
            return SolutionCandidate(output=actions, solution_kind="world_plan")
        return SolutionCandidate(output=None, solution_kind="unknown")

    def critique(self, task: TaskInput, solution: SolutionCandidate, *, seed: int) -> str:
        return ""


def _plan_world_actions(world: GridWorld) -> list[str]:
    actions: list[str] = []
    world.reset(seed=0)
    while world.agent != world.goal:
        ax, ay = world.agent
        gx, gy = world.goal
        if ax < gx:
            actions.append("right")
            world.step("right")
            continue
        if ay < gy:
            actions.append("down")
            world.step("down")
            continue
        if ax > gx:
            actions.append("left")
            world.step("left")
            continue
        if ay > gy:
            actions.append("up")
            world.step("up")
            continue
    return actions
