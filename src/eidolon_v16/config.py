from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    artifact_store: Path
    ledger_db: Path
    ledger_chain: Path
    runs_dir: Path
    skills_dir: Path
    skills_registry: Path
    language_dir: Path
    language_registry: Path


@dataclass(frozen=True)
class AppConfig:
    paths: Paths


def default_paths(root: Path | None = None) -> Paths:
    base = root or Path.cwd()
    runs_env = os.getenv("EIDOLON_RUNS_DIR", "").strip()
    ledger_env = os.getenv("EIDOLON_LEDGER_CHAIN", "").strip()
    skills_env = os.getenv("EIDOLON_SKILLS_DIR", "").strip()
    language_env = os.getenv("EIDOLON_LANGUAGE_DIR", "").strip()
    language_reg_env = os.getenv("EIDOLON_LANGUAGE_REGISTRY", "").strip()
    runs_dir = Path(runs_env) if runs_env else base / "runs"
    ledger_chain = Path(ledger_env) if ledger_env else base / "ledger.chain.jsonl"
    skills_dir = Path(skills_env) if skills_env else base / "skills"
    language_dir = Path(language_env) if language_env else base / "language"
    language_registry = (
        Path(language_reg_env)
        if language_reg_env
        else language_dir / "registry.json"
    )
    return Paths(
        root=base,
        artifact_store=base / "artifact_store",
        ledger_db=base / "ledger.db",
        ledger_chain=ledger_chain,
        runs_dir=runs_dir,
        skills_dir=skills_dir,
        skills_registry=base / "skills" / "registry.json",
        language_dir=language_dir,
        language_registry=language_registry,
    )


def default_config(root: Path | None = None) -> AppConfig:
    return AppConfig(paths=default_paths(root))
