from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def test_truth_spine_includes_verify_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    oracle = bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict()
    spec = {
        "name": "x_plus_one",
        "inputs": [["x", "Int"]],
        "output": "Int",
        "examples": [{"in": {"x": 2}, "out": 3}],
        "bounds": {"max_depth": 2, "max_programs": 500, "fuzz_trials": 3},
        "oracle": oracle,
    }
    spec_json = json.dumps(spec, separators=(",", ":"), sort_keys=True)
    prompt = f"BVPS_SPEC:{spec_json}"

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-verify",
            "kind": "unknown",
            "prompt": prompt,
            "data": {},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    ucr_payload = json.loads(result.ucr_path.read_text())
    manifest = ucr_payload.get("artifact_manifest", [])
    manifest_paths = {entry["path"] for entry in manifest}
    assert "verify/consequence_bvps.json" in manifest_paths
    assert "verify/translation_bvps.json" in manifest_paths

    witness_payload = json.loads(result.witness_path.read_text())
    evidence_paths = []
    for lane in witness_payload.get("verification", []):
        for ref in lane.get("evidence", []):
            path = ref.get("path")
            if isinstance(path, str):
                evidence_paths.append(path)
    assert "verify/consequence_bvps.json" in evidence_paths
    assert "verify/translation_bvps.json" in evidence_paths
