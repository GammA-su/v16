from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.config import default_config
from eidolon_v16.ledger.chain import verify_chain
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.canonical import compute_ucr_hash
from eidolon_v16.ucr.models import TaskInput


def test_episode_bvps_truth_spine_artifacts(
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
        "bounds": {"max_depth": 2, "max_programs": 500, "fuzz_trials": 5},
        "oracle": oracle,
    }
    spec_json = json.dumps(spec, separators=(",", ":"), sort_keys=True)
    prompt = f"BVPS_SPEC:{spec_json}"

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-episode",
            "kind": "unknown",
            "prompt": prompt,
            "data": {},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    run_dir = config.paths.runs_dir / result.ucr_path.parent.name
    artifacts_dir = run_dir / "artifacts" / "bvps"
    assert artifacts_dir.exists()
    assert any(artifacts_dir.iterdir())

    ucr_payload = json.loads(result.ucr_path.read_text())
    assert ucr_payload["hashes"]["ucr_hash"] == compute_ucr_hash(ucr_payload)
    manifest = ucr_payload.get("artifact_manifest", [])
    assert any(entry["path"].startswith("bvps/") for entry in manifest)

    ok, err = verify_chain(config.paths.ledger_chain)
    assert ok is True
    assert err is None


def test_run_folder_evidence_files_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    oracle = bvps_ast.BinOp("add", bvps_ast.Var("x"), bvps_ast.IntConst(1)).to_dict()
    spec = {
        "name": "x_plus_one",
        "inputs": [["x", "Int"]],
        "output": "Int",
        "examples": [{"in": {"x": 2}, "out": 3}],
        "bounds": {"max_depth": 2, "max_programs": 500, "fuzz_trials": 5},
        "oracle": oracle,
    }
    prompt = f"BVPS_SPEC:{json.dumps(spec, separators=(',', ':'), sort_keys=True)}"

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "bvps-episode-evidence",
            "kind": "unknown",
            "prompt": prompt,
            "data": {},
        }
    )
    result = controller.run(task=task, mode=ModeConfig(seed=0, use_gpu=False))

    run_dir = result.ucr_path.parent
    artifacts_dir = run_dir / "artifacts"
    ucr_payload = json.loads(result.ucr_path.read_text())
    lane_verdicts = ucr_payload.get("lane_verdicts", {})
    for verdict in lane_verdicts.values():
        for evidence in verdict.get("evidence", []):
            ext = controller._artifact_extension(evidence["media_type"])
            path = artifacts_dir / f"{evidence['type']}-{evidence['hash']}{ext}"
            assert path.exists(), f"Missing artifact for {evidence['type']}"
