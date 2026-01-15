from __future__ import annotations

import json
import logging
import tarfile
import tempfile
from pathlib import Path

from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.runtime import initialize_runtime
from eidolon_v16.ucr.models import TaskInput

logger = logging.getLogger(__name__)


def replay_capsule_tar(path: Path, controller: EpisodeController, seed: int = 0) -> bool:
    mode = ModeConfig(seed=seed)
    initialize_runtime(
        cpu_threads=mode.cpu_threads,
        use_gpu=mode.use_gpu,
        gpu_id=mode.gpu_id,
        logger=logger,
    )
    logger.info("capsule replay start path=%s", path)
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(path) as tar:
            tar.extractall(tmpdir)
        task_path = Path(tmpdir) / "task.json"
        if not task_path.exists():
            logger.warning("capsule replay missing task.json")
            return False
        task = TaskInput.model_validate(json.loads(task_path.read_text()))
    controller.run(task, mode)
    logger.info("capsule replay complete")
    return True
