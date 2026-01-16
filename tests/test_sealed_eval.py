from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.cli import eval_sealed
from eidolon_v16.config import default_config
from eidolon_v16.eval import sealed_eval as sealed_eval_module
from eidolon_v16.eval.sealed_eval import run_sealed_eval
from eidolon_v16.orchestrator.types import ModeConfig


def test_sealed_eval_report_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sealed_eval_module,
        "ModeConfig",
        lambda **kwargs: ModeConfig(use_gpu=False, **kwargs),
    )
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: basic",
                "generators:",
                "  - kind: arith",
                "    weight: 1",
                "  - kind: list",
                "    weight: 1",
                "  - kind: world",
                "    weight: 1",
                "",
            ]
        )
    )
    config = default_config(root=tmp_path)
    result = run_sealed_eval(
        config=config,
        suite_path=suite_path,
        n=5,
        seed=123,
        reveal_seed=False,
    )
    assert result.report_path.exists()
    payload = json.loads(result.report_path.read_text())
    assert payload["suite_name"] == "basic"
    assert payload["commitment_hash"]
    assert len(payload["results"]) == 5
    assert "sealed_tasks_artifact" in payload

    store = ArtifactStore(config.paths.artifact_store)
    tasks_ref = payload["sealed_tasks_artifact"]
    tasks = cast(list[dict[str, Any]], store.read_json_by_hash(tasks_ref["hash"]))
    for task in tasks:
        assert "expected" not in task
        assert "expected" not in task.get("data", {})


def test_sealed_eval_seed_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sealed_eval_module,
        "ModeConfig",
        lambda **kwargs: ModeConfig(use_gpu=False, **kwargs),
    )
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_name: basic",
                "generators:",
                "  - kind: arith",
                "    weight: 1",
                "",
            ]
        )
    )
    monkeypatch.chdir(tmp_path)
    eval_sealed(suite=suite_path, n=1, seed=7, reveal_seed=False)
    output = capsys.readouterr().out
    assert "Seed:" not in output
    eval_sealed(suite=suite_path, n=1, seed=7, reveal_seed=True)
    output = capsys.readouterr().out
    assert "Seed:" in output
