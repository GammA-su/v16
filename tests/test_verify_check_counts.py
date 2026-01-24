from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


def test_verify_check_counts_per_run_and_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    task = _load_task(Path("examples/tasks/arith_01.json"))
    result = controller.run(task=task, mode=mode)
    payload = json.loads(result.ucr_path.read_text())
    costs = payload.get("costs", {})
    verify_counts = costs.get("verify_checks_count", {})
    assert isinstance(verify_counts, dict)
    assert verify_counts.get("verify_domain_count") == 1
    assert verify_counts.get("verify_format_count") == 1
    assert verify_counts.get("verify_task_verifier_count") == 1

    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: verify-check-counts",
                "tasks:",
                "  - arith_01",
                "seeds: [0]",
                "",
            ]
        )
    )
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    report_payload = json.loads(report.report_path.read_text())
    metrics = report_payload.get("metrics", {})
    assert metrics.get("verify_checks_verify_domain_count") == 1
    assert metrics.get("verify_checks_verify_format_count") == 1
    assert metrics.get("verify_checks_verify_task_verifier_count") == 1

    runs = report_payload.get("runs", [])
    assert isinstance(runs, list)
    run = runs[0]
    assert run.get("verify_check_verify_domain_count") == 1
    assert run.get("verify_check_verify_format_count") == 1
    assert run.get("verify_check_verify_task_verifier_count") == 1
