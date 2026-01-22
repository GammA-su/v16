from __future__ import annotations

import json
from pathlib import Path

from eidolon_v16.config import default_config
from eidolon_v16.eval.suite import run_suite


def _write_suite(path: Path) -> None:
    task_one = Path("examples/tasks/arith_01.json").resolve()
    task_two = Path("examples/tasks/arith_edge_01.json").resolve()
    path.write_text(
        "\n".join(
            [
                "suite_name: manifest-guard",
                "tasks:",
                "  - name: arith_01",
                f"    path: {task_one}",
                "  - name: arith_edge_01",
                f"    path: {task_two}",
                "seeds:",
                "  - 0",
            ]
        )
    )


def test_perf_suite_manifest_per_suite_guard(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    suite_path = tmp_path / "suite.yaml"
    _write_suite(suite_path)
    config = default_config(root=tmp_path)
    report = run_suite(config=config, suite_path=suite_path, out_dir=tmp_path / "out")
    payload = json.loads(report.report_path.read_text())

    metrics = payload.get("metrics", {})
    assert isinstance(metrics, dict)
    assert metrics.get("store_manifest_flush_mode") == "per_suite"
    assert int(metrics.get("suite_store_manifest_flush_count", 0)) == 1
    assert int(metrics.get("verify_store_manifest_ms_p95", 0)) == 0
    assert int(metrics.get("suite_store_manifest_flush_ms", 0)) > 0
