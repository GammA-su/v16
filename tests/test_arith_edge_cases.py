from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.utils import safe_eval_arith


@pytest.mark.parametrize(
    "prompt, expected_expr",
    [
        ("ARITH:   -3 + 5", "-3 + 5"),
        ("arith: ( (2 + 3) * (4 - 1))", "( (2 + 3) * (4 - 1))"),
        ("  ARITH: 7 / 2", "7 / 2"),
        ("ARITH: ((2 + 3) * (4 + (1 - 2)))", "((2 + 3) * (4 + (1 - 2)))"),
        ("ARITH: (10**20 + 1) * 2", "(10**20 + 1) * 2"),
        ("ARITH: -(-5) + 2", "-(-5) + 2"),
        ("ARITH: (((1 + 2) * (3 + 4)) - (5 - 6))", "(((1 + 2) * (3 + 4)) - (5 - 6))"),
        ("ARITH: (10**30 + 123456789) * 2", "(10**30 + 123456789) * 2"),
        ("ARITH:   7   *   (  8 +  2  )", "7   *   (  8 +  2  )"),
    ],
    ids=[
        "unary-minus-whitespace",
        "lowercase-prefix",
        "leading-whitespace-div",
        "nested-parentheses",
        "big-int-pow",
        "double-unary-minus",
        "deep-parentheses",
        "bigger-int-pow",
        "extra-whitespace",
    ],
)
def test_arith_edge_cases_pass(
    tmp_path: Path, prompt: str, expected_expr: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": f"edge-{expected_expr}",
            "task": prompt,
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    ucr_payload = json.loads(result.ucr_path.read_text())
    statuses = [lane["status"] for lane in ucr_payload["verification"]]
    assert all(status == "PASS" for status in statuses)

    store = ArtifactStore(config.paths.artifact_store)
    solution_hash = ucr_payload["solution_artifacts"][0]["hash"]
    solution_payload = store.read_json_by_hash(solution_hash)
    assert solution_payload["expression"] == expected_expr
    assert solution_payload["output"] == safe_eval_arith(expected_expr)


@pytest.mark.parametrize(
    "prompt",
    [
        "ARITH: 2 << 1",
        "ARITH: 3 & 4",
    ],
    ids=["unsupported-shift", "unsupported-bitand"],
)
def test_arith_invalid_expression_refuses(
    tmp_path: Path, prompt: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "arith-invalid",
            "task": prompt,
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    ucr_payload = json.loads(result.ucr_path.read_text())
    assert ucr_payload["decision"]["action"] == "refuse"
    recompute_lane = next(
        lane for lane in ucr_payload["verification"] if lane["lane"] == "recompute"
    )
    store = ArtifactStore(config.paths.artifact_store)
    evidence_payload = store.read_json_by_hash(recompute_lane["evidence"][0]["hash"])
    assert "error" in evidence_payload
