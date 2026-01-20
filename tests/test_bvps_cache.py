from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.sealed_eval import run_sealed_eval
from eidolon_v16.eval.suite import run_suite
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput
from eidolon_v16.bvps import cegis as bvps_cegis


def _write_bvps_suite(path: Path, seeds: list[int]) -> None:
    path.write_text(
        "\n".join(
            [
                "suite_name: bvps-cache",
                "tasks:",
                "  - name: bvps_abs_01",
                "    path: examples/tasks/bvps_abs_01.json",
                "seeds:",
            ]
            + [f"  - {seed}" for seed in seeds]
        )
    )


def _scrub_witness(payload: dict[str, object]) -> dict[str, object]:
    scrubbed = json.loads(json.dumps(payload))
    for key in ("episode_id", "run_dir", "replay", "artifact_refs", "ucr_hash"):
        scrubbed.pop(key, None)
    costs = scrubbed.get("costs")
    if isinstance(costs, dict):
        for key in (
            "total_ms",
            "solve_wall_ms",
            "phase_ms",
            "lane_ms",
            "verifier_ms",
            "verify_breakdown_ms",
            "solve_breakdown_ms",
            "bvps_cache",
            "bvps_cache_meta",
            "bvps_cache_state",
            "bvps_ids",
            "bvps_fastpath",
        ):
            costs.pop(key, None)
    verification = scrubbed.get("verification")
    if isinstance(verification, list):
        for lane in verification:
            if not isinstance(lane, dict):
                continue
            lane.pop("cost_ms", None)
            lane.pop("costs", None)
            lane.pop("evidence", None)
    return scrubbed


def test_bvps_cache_reuses_synthesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite_file = tmp_path / "suite.yaml"
    _write_bvps_suite(suite_file, seeds=[0, 1, 2, 3])

    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")
    config = default_config(root=tmp_path)
    calls = {"count": 0}
    original = bvps_cegis.synthesize

    def wrapped(*args: object, **kwargs: object):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(bvps_cegis, "synthesize", wrapped)
    run_suite(config=config, suite_path=suite_file, out_dir=tmp_path / "out")
    assert calls["count"] <= 1


def test_bvps_cache_witness_stable_and_sealed_commitment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_payload = json.loads(Path("examples/tasks/bvps_abs_01.json").read_text())
    task = TaskInput.from_raw(task_payload)
    mode = ModeConfig(seed=0, use_gpu=False)

    monkeypatch.delenv("EIDOLON_BVPS_PERSIST_CACHE", raising=False)
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "1")
    base_config = default_config(root=tmp_path / "base")
    base_controller = EpisodeController(config=base_config)
    base_result = base_controller.run(task=task, mode=mode)
    base_witness = json.loads(base_result.witness_path.read_text())

    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_CACHE", "1")
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "1")
    cache_config = default_config(root=tmp_path / "cache")
    populate_controller = EpisodeController(config=cache_config)
    populate_controller.run(task=task, mode=mode)
    cached_controller = EpisodeController(config=cache_config)
    cached_result = cached_controller.run(task=task, mode=mode)
    cached_witness = json.loads(cached_result.witness_path.read_text())

    assert _scrub_witness(base_witness) == _scrub_witness(cached_witness)

    sealed_suite = tmp_path / "sealed.yaml"
    sealed_suite.write_text(
        "\n".join(
            [
                "suite_name: sealed-cache",
                "generators:",
                "  - kind: arith",
                "    weight: 1",
            ]
        )
    )
    sealed_config = default_config(root=tmp_path / "sealed")
    monkeypatch.delenv("EIDOLON_BVPS_PERSIST_CACHE", raising=False)
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "1")
    first = run_sealed_eval(
        config=sealed_config,
        suite_path=sealed_suite,
        n=3,
        seed=123,
        reveal_seed=True,
    )
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST_CACHE", "1")
    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "1")
    second = run_sealed_eval(
        config=sealed_config,
        suite_path=sealed_suite,
        n=3,
        seed=123,
        reveal_seed=True,
    )
    assert first.commitment_hash == second.commitment_hash
