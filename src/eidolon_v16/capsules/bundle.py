from __future__ import annotations

import io
import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from eidolon_v16.artifacts.store import ArtifactRef, ArtifactStore
from eidolon_v16.ucr.canonical import canonical_json_bytes
from eidolon_v16.ucr.models import Decision, Interpretation, LaneVerdict, TaskInput

logger = logging.getLogger(__name__)


def build_capsule(
    *,
    store: ArtifactStore,
    episode_id: str,
    task: TaskInput,
    interpretation: Interpretation,
    solution: dict[str, Any],
    lanes: list[LaneVerdict],
    decision: Decision,
) -> ArtifactRef:
    capsule_type = "capsule_success" if decision.action == "answer" else "capsule_failure"
    logger.info("capsule build start type=%s", capsule_type)
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        (base / "task.json").write_bytes(canonical_json_bytes(task.model_dump(mode="json")))
        (base / "interpretation.json").write_bytes(
            canonical_json_bytes(interpretation.model_dump(mode="json"))
        )
        (base / "solution.json").write_bytes(canonical_json_bytes(solution))
        (base / "lanes.json").write_bytes(
            canonical_json_bytes([lane.model_dump(mode="json") for lane in lanes])
        )
        (base / "decision.json").write_bytes(canonical_json_bytes(decision.model_dump(mode="json")))
        repro = f"uv run eidolon episode replay --ucr runs/{episode_id}/ucr.json\n"
        (base / "repro.txt").write_text(repro)
        data = _tar_directory(base)
    ref = store.put_bytes(
        data,
        artifact_type=capsule_type,
        media_type="application/x-tar",
        producer="capsules",
    )
    logger.info("capsule build complete hash=%s", ref.hash)
    return ref


def _tar_directory(path: Path) -> bytes:
    fileobj = io.BytesIO()
    with tarfile.open(fileobj=fileobj, mode="w") as tar:
        for item in sorted(path.rglob("*")):
            if item.is_file():
                tar.add(item, arcname=item.relative_to(path))
    return fileobj.getvalue()
