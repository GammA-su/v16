from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from eidolon_v16.ucr.models import TaskInput


@dataclass(frozen=True)
class ModeConfig:
    seed: int = 0
    required_lanes: list[str] = field(
        default_factory=lambda: ["recompute", "translation", "consequence", "anchors"]
    )
    use_gpu: bool = True
    gpu_id: int = 1
    cpu_threads: int = 16


@dataclass(frozen=True)
class EpisodeResult:
    ucr_path: Path
    witness_path: Path
    ucr_hash: str


__all__ = ["TaskInput", "ModeConfig", "EpisodeResult"]
