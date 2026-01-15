from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eidolon_v16.artifacts.store import ArtifactRef


class TaskInput(BaseModel):
    raw: dict[str, Any]
    normalized: dict[str, Any]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TaskInput:
        normalized = normalize_task(raw)
        return cls(raw=raw, normalized=normalized)


class AmbiguitySlot(BaseModel):
    slot_id: str
    description: str
    values: list[str] = Field(default_factory=list)


class Interpretation(BaseModel):
    interpretation_id: str
    description: str
    assumptions: list[str] = Field(default_factory=list)
    ambiguity_slots: list[AmbiguitySlot] = Field(default_factory=list)


class LaneVerdict(BaseModel):
    lane: str
    status: Literal["PASS", "FAIL", "BORDERLINE"]
    evidence: list[ArtifactRef] = Field(default_factory=list)
    notes: str | None = None


class Budget(BaseModel):
    steps: int
    cpu_ms: int
    notes: str | None = None


class Decision(BaseModel):
    action: Literal["answer", "ask", "branch", "refuse"]
    rationale: str
    assumptions: list[str] = Field(default_factory=list)


class HashCommitments(BaseModel):
    ucr_hash: str
    artifact_manifest_hash: str


class UCR(BaseModel):
    episode_id: str
    schema_version: str
    task_input: TaskInput
    interpretations: list[Interpretation]
    chosen_interpretation_id: str
    decision: Decision
    solution_artifacts: list[ArtifactRef]
    verification: list[LaneVerdict]
    budgets: Budget
    final_result: str
    hashes: HashCommitments
    witness_packet: ArtifactRef


class WitnessPacket(BaseModel):
    episode_id: str
    final_response: str
    interpretations: list[Interpretation]
    chosen_interpretation_id: str
    artifact_refs: list[ArtifactRef]
    verification: list[LaneVerdict]
    budgets: Budget
    replay: list[str]


def normalize_task(raw: dict[str, Any]) -> dict[str, Any]:
    task_id = str(raw.get("task_id") or raw.get("id") or "task-unknown")
    kind = str(raw.get("kind") or raw.get("type") or "unknown")
    prompt = str(raw.get("prompt") or raw.get("task") or "")
    data = raw.get("data")
    if data is None:
        skip = {"task_id", "id", "kind", "type", "prompt", "task"}
        data = {k: v for k, v in raw.items() if k not in skip}
    return {
        "task_id": task_id,
        "kind": kind,
        "prompt": prompt,
        "data": data,
    }
