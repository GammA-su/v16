from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "report_migrate", Path("scripts/report_migrate.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_migrate_smoke(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    legacy = {
        "runs": [
            {"verify_checks_ms": {"verify_domain_ms": 1, "verify_format_ms": 2}},
            {"verify_checks_ms": {"verify_domain_ms": 1}},
        ],
        "metrics": {},
    }
    report_path.write_text(json.dumps(legacy))

    module = _load_module()
    migrated = module.migrate_report(json.loads(report_path.read_text()))
    meta = migrated.get("report_meta", {})
    assert isinstance(meta, dict)
    assert meta.get("created_utc")
    assert meta.get("git_sha")
    assert meta.get("host")
    assert meta.get("python")

    metrics = migrated.get("metrics", {})
    assert metrics.get("verify_checks_verify_domain_count") == 2
    assert metrics.get("verify_checks_verify_format_count") == 1
    assert metrics.get("verify_checks_verify_task_verifier_count") == 0

    runs = migrated.get("runs", [])
    assert runs[0].get("verify_check_verify_domain_count") == 1
    assert runs[0].get("verify_check_verify_format_count") == 1
    assert runs[1].get("verify_check_verify_domain_count") == 1
    assert "verify_check_verify_domain_ms" in runs[0]
    assert "verify_check_verify_format_ms" in runs[0]
    assert "verify_check_verify_task_verifier_ms" in runs[0]
    runs[0]["overhead_breakdown_ms"] = {"postsolve_detail_ms": {"artifact_plan_ms": 5}}
    runs[0]["verify_task_verifier_detail_ms"] = {"tv_exec_ms": 7}
    migrated = module.migrate_report(migrated)
    assert "postsolve_detail_artifact_plan_ms" in migrated["runs"][0]
    assert "verify_task_verifier_detail_tv_exec_ms" in migrated["runs"][0]
