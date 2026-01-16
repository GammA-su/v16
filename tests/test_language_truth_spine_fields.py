from __future__ import annotations

from eidolon_v16.artifacts.store import ArtifactRef
from eidolon_v16.ucr.models import (
    UCR,
    Budget,
    Decision,
    HashCommitments,
    LaneVerdict,
    TaskInput,
    WitnessPacket,
)


def _make_artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        hash="dummy",
        type="solution",
        media_type="application/json",
        size=0,
    )


def test_truth_spine_includes_language_patch_field() -> None:
    budgets = Budget(steps=0, cpu_ms=0)
    decision = Decision(action="answer", rationale="ok", assumptions=[])
    task_input = TaskInput(raw={}, normalized={})
    artifact_ref = _make_artifact_ref()
    lane = LaneVerdict(lane="recompute", status="PASS")

    witness = WitnessPacket(
        episode_id="ep-test",
        final_response="result",
        interpretations=[],
        chosen_interpretation_id="interp",
        artifact_refs=[artifact_ref],
        verification=[lane],
        budgets=budgets,
        replay=[],
    )
    assert witness.active_language_patches == []

    ucr = UCR(
        episode_id="ep-test",
        schema_version="ucr/v1",
        ts_utc="2025-01-01T00:00:00Z",
        task_text="Compute 1 + 1",
        task_input=task_input,
        interpretations=[],
        chosen_interpretation_id="interp",
        budgets=budgets,
        kernel={"kind": "stub"},
        solution={"solution_kind": "arith_eval", "output": 2},
        lane_verdicts={"recompute": {"status": "PASS"}},
        costs={},
        artifact_manifest=[],
        decision=decision,
        solution_artifacts=[],
        verification=[lane],
        final_result="result",
        hashes=HashCommitments(ucr_hash="", artifact_manifest_hash=""),
        witness_packet=ArtifactRef(
            hash="dummy",
            type="witness_packet",
            media_type="application/json",
            size=0,
        ),
    )
    assert ucr.active_language_patches == []
