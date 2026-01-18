from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eidolon_v16.artifacts.store import ArtifactRef
from eidolon_v16.bvps.prompt import parse_bvps_prompt


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
    cost_ms: int = 0
    evidence: list[ArtifactRef] = Field(default_factory=list)
    notes: str | None = None
    costs: dict[str, Any] = Field(default_factory=dict)


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
    run_dir: str
    ts_utc: str = ""
    task_text: str = ""
    task_input: TaskInput
    interpretations: list[Interpretation]
    chosen_interpretation_id: str | None
    budgets: Budget
    kernel: dict[str, Any] = Field(default_factory=dict)
    solution: dict[str, Any] = Field(default_factory=dict)
    lane_verdicts: dict[str, Any] = Field(default_factory=dict)
    costs: dict[str, Any] = Field(default_factory=dict)
    artifact_manifest: list[dict[str, Any]] = Field(default_factory=list)
    decision: Decision
    solution_artifacts: list[ArtifactRef]
    verification: list[LaneVerdict]
    final_result: str
    hashes: HashCommitments
    ucr_hash: str = ""
    witness_packet: ArtifactRef
    used_skill: dict[str, Any] | None = None
    admitted_skill: dict[str, Any] | None = None
    active_language_patches: list[dict[str, Any]] = Field(default_factory=list)


class WitnessPacket(BaseModel):
    episode_id: str
    run_dir: str
    final_response: str
    interpretations: list[Interpretation]
    chosen_interpretation_id: str
    artifact_refs: list[ArtifactRef]
    verification: list[LaneVerdict]
    budgets: Budget
    replay: list[str]
    costs: dict[str, Any] = Field(default_factory=dict)
    used_skill: dict[str, Any] | None = None
    admitted_skill: dict[str, Any] | None = None
    active_language_patches: list[dict[str, Any]] = Field(default_factory=list)


def normalize_task(raw: dict[str, Any]) -> dict[str, Any]:
    task_id = str(raw.get("task_id") or raw.get("id") or "task-unknown")
    kind_raw = str(raw.get("kind") or raw.get("type") or "")
    prompt = str(raw.get("prompt") or raw.get("task") or "")
    kind = _infer_kind(kind_raw, prompt)
    data = raw.get("data")
    if data is None:
        skip = {"task_id", "id", "kind", "type", "prompt", "task"}
        data = {k: v for k, v in raw.items() if k not in skip}
    _maybe_attach_bvps_spec(kind, data, prompt)
    return {
        "task_id": task_id,
        "kind": kind,
        "prompt": prompt,
        "data": data,
    }


def _infer_kind(kind_raw: str, prompt: str) -> str:
    candidate = kind_raw.strip()
    normalized = prompt.strip().upper()
    if candidate and candidate.lower() != "unknown":
        return candidate
    if normalized.startswith("ARITH:"):
        return "arith"
    if normalized.startswith("BVPS:") or normalized.startswith("SYNTH:"):
        return "bvps"
    return "unknown"


def _maybe_attach_bvps_spec(kind: str, data: Any, prompt: str) -> None:
    if kind != "bvps":
        return
    if not isinstance(data, dict):
        return
    spec = data.get("bvps_spec")
    if isinstance(spec, dict):
        return
    inferred = parse_bvps_prompt(prompt)
    if inferred is not None:
        data["bvps_spec"] = inferred
