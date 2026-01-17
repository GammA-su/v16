from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from eidolon_v16.config import default_config
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.ucr.canonical import compute_ucr_hash
from eidolon_v16.ucr.models import TaskInput


def _solution_files(run_dir: Path) -> list[Path]:
    return sorted((run_dir / "artifacts").glob("solution-*.json"))


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_run_dirs_are_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)

    config = default_config(root=tmp_path)
    controller = EpisodeController(config=config)
    task = TaskInput.from_raw(
        {
            "task_id": "run-dir-test",
            "kind": "arith",
            "prompt": "ARITH: 4 * 5",
            "data": {"expression": "4 * 5"},
        }
    )
    mode = ModeConfig(seed=0, use_gpu=False)
    result1 = controller.run(task=task, mode=mode)
    result2 = controller.run(task=task, mode=mode)

    run_dir1 = result1.ucr_path.parent
    run_dir2 = result2.ucr_path.parent
    assert run_dir1 != run_dir2

    ucr1 = _read_json(result1.ucr_path)
    ucr2 = _read_json(result2.ucr_path)
    episode_id = str(ucr1["episode_id"])
    assert str(ucr2["episode_id"]) == episode_id
    assert result1.ucr_hash != result2.ucr_hash
    assert ucr1["run_dir"] == str(run_dir1)
    assert ucr2["run_dir"] == str(run_dir2)
    assert run_dir1.name == Path(str(ucr1["run_dir"])).name
    assert run_dir2.name == f"{episode_id}-r01"

    witness1 = _read_json(result1.witness_path)
    witness2 = _read_json(result2.witness_path)
    assert witness1["run_dir"] == str(run_dir1)
    assert witness2["run_dir"] == str(run_dir2)

    hashes1 = cast(dict[str, object], ucr1["hashes"])
    hashes2 = cast(dict[str, object], ucr2["hashes"])
    assert compute_ucr_hash(ucr1) == str(hashes1["ucr_hash"])
    assert compute_ucr_hash(ucr2) == str(hashes2["ucr_hash"])
    assert _solution_files(run_dir1)
    assert _solution_files(run_dir2)
