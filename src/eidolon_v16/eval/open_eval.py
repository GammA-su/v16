from __future__ import annotations

import json
import logging
from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import AppConfig
from eidolon_v16.eval.generators import generate_open_tasks
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig
from eidolon_v16.runtime import initialize_runtime
from eidolon_v16.ucr.models import TaskInput

logger = logging.getLogger(__name__)


def run_open_eval(config: AppConfig, n: int, seed: int) -> Path:
    mode = ModeConfig(seed=seed)
    initialize_runtime(
        cpu_threads=mode.cpu_threads,
        use_gpu=mode.use_gpu,
        gpu_id=mode.gpu_id,
        logger=logger,
    )
    store = ArtifactStore(config.paths.artifact_store)
    controller = EpisodeController(config=config)
    tasks = generate_open_tasks(n=n, seed=seed)

    results = []
    canary_hits = 0
    for idx, raw in enumerate(tasks, start=1):
        logger.info("open eval task %s/%s", idx, len(tasks))
        task = TaskInput.from_raw(raw)
        result = controller.run(task, mode)
        witness_data = json.loads(Path(result.witness_path).read_text())
        if "CANARY-DO-NOT-EMIT" in str(witness_data.get("final_response", "")):
            canary_hits += 1
        results.append(
            {
                "task_id": task.normalized["task_id"],
                "ucr_hash": result.ucr_hash,
                "ucr_path": str(result.ucr_path),
            }
        )

    report = {
        "total": len(results),
        "canary_hits": canary_hits,
        "results": results,
    }
    report_ref = store.put_json(report, artifact_type="eval_open_report", producer="eval")
    report_path = store.path_for_hash(report_ref.hash)
    logger.info("open eval complete report=%s", report_path)
    return report_path
