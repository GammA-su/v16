from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from eidolon_v16.ucr.models import Interpretation, TaskInput


@dataclass(frozen=True)
class SolutionCandidate:
    output: Any
    solution_kind: str
    program: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None


class Kernel(Protocol):
    def propose_interpretations(self, task: TaskInput, *, seed: int) -> list[Interpretation]:
        ...

    def propose_solution(
        self, task: TaskInput, interpretation: Interpretation, *, seed: int
    ) -> SolutionCandidate:
        ...

    def critique(self, task: TaskInput, solution: SolutionCandidate, *, seed: int) -> str:
        ...
