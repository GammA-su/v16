from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon_v16.bvps import cegis as bvps_cegis
from eidolon_v16.bvps import enumerate as bvps_enumerate
from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def _write_abs_suite(path: Path, seeds: list[int]) -> None:
    path.write_text(
        "\n".join(
            [
                "suite_name: bvps-abs-only",
                "tasks:",
                "  - name: bvps_abs_01",
                "    path: examples/tasks/bvps_abs_01.json",
                "seeds:",
            ]
            + [f"  - {seed}" for seed in seeds]
        )
    )


def test_bvps_cache_hits_abs_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suite_file = tmp_path / "suite.yaml"
    _write_abs_suite(suite_file, seeds=[0, 1, 2, 3])

    monkeypatch.setenv("EIDOLON_BVPS_FASTPATH", "0")
    monkeypatch.setenv("EIDOLON_BVPS_PERSIST", "0")
    config = default_config(root=tmp_path)
    calls = {"synth": 0, "enum": 0}
    original_synth = bvps_cegis.synthesize
    original_enum = bvps_enumerate.enumerate_programs

    def wrapped(*args: object, **kwargs: object):
        calls["synth"] += 1
        return original_synth(*args, **kwargs)

    def enum_wrapped(*args: object, **kwargs: object):
        calls["enum"] += 1
        return original_enum(*args, **kwargs)

    monkeypatch.setattr(bvps_cegis, "synthesize", wrapped)
    monkeypatch.setattr(bvps_enumerate, "enumerate_programs", enum_wrapped)
    report = run_suite(config=config, suite_path=suite_file, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())
    runs = payload.get("runs", [])
    hits = 0
    misses = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        cache_state = run.get("bvps_cache")
        if isinstance(cache_state, str) and cache_state:
            if cache_state.startswith("hit:"):
                hits += 1
            else:
                misses += 1
            continue
        cache = run.get("bvps_cache_meta", {})
        if not isinstance(cache, dict) or "hit" not in cache:
            continue
        if cache.get("hit"):
            hits += 1
        else:
            misses += 1
    assert hits == 3
    assert misses == 1
    assert calls["synth"] <= 1
    assert calls["enum"] <= 1
