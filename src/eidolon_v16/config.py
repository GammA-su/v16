from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    artifact_store: Path
    ledger_db: Path
    runs_dir: Path
    skills_registry: Path


@dataclass(frozen=True)
class AppConfig:
    paths: Paths


def default_paths(root: Path | None = None) -> Paths:
    base = root or Path.cwd()
    return Paths(
        root=base,
        artifact_store=base / "artifact_store",
        ledger_db=base / "ledger.db",
        runs_dir=base / "runs",
        skills_registry=base / "skills" / "registry.json",
    )


def default_config(root: Path | None = None) -> AppConfig:
    return AppConfig(paths=default_paths(root))
