from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.models import TaskInput


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


def _run_bvps_abs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, reverify: bool
) -> tuple[EpisodeController, Path]:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    monkeypatch.setenv("EIDOLON_AUTO_SKILLS", "1")
    monkeypatch.setenv("EIDOLON_ADMISSION_REVERIFY", "1" if reverify else "0")
    monkeypatch.setenv("EIDOLON_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EIDOLON_SKILLS_DIR", str(tmp_path / "skills"))

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    mode = ModeConfig(seed=0, use_gpu=False)

    task = _load_task(Path("examples/tasks/bvps_abs_01.json"))
    result = controller.run(task=task, mode=mode)
    return controller, result.ucr_path


def test_no_reverify_admitted_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _controller, ucr_path1 = _run_bvps_abs(tmp_path, monkeypatch, reverify=False)
    admission_path = tmp_path / "skills" / "abs" / "admission_verdict.json"
    assert admission_path.exists()

    _controller, ucr_path2 = _run_bvps_abs(tmp_path, monkeypatch, reverify=False)
    payload = json.loads(ucr_path2.read_text())
    assert payload.get("admitted_skill") is not None
    run_dir = ucr_path2.parent
    assert not (run_dir / "skills").exists()
    verify_breakdown = payload.get("costs", {}).get("verify_breakdown_ms", {})
    assert isinstance(verify_breakdown, dict)
    assert int(verify_breakdown.get("verify_admission_ms", 0)) <= 2


def test_reverify_admitted_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _controller, _ucr_path1 = _run_bvps_abs(tmp_path, monkeypatch, reverify=False)
    _controller, ucr_path2 = _run_bvps_abs(tmp_path, monkeypatch, reverify=True)
    payload = json.loads(ucr_path2.read_text())
    run_dir = ucr_path2.parent
    assert (run_dir / "skills").exists()
    verify_breakdown = payload.get("costs", {}).get("verify_breakdown_ms", {})
    assert isinstance(verify_breakdown, dict)
    assert int(verify_breakdown.get("verify_admission_ms", 0)) > 0
