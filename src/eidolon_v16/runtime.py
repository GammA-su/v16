from __future__ import annotations

import importlib
import logging
import os
import threading
from typing import Any

_DEFAULT_THREADS = 16
_DEFAULT_GPU_ID = 0

_runtime_lock = threading.Lock()
_runtime_initialized = False
_faiss_gpu_checked = False
_faiss_gpu_ready = False


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _load_faiss() -> Any:
    return importlib.import_module("faiss")


def configure_threads(num_threads: int) -> None:
    thread_value = str(num_threads)
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(key, thread_value)
    try:
        faiss = _load_faiss()
        faiss.omp_set_num_threads(num_threads)
    except Exception:
        pass


def init_faiss_gpu(gpu_id: int, logger: logging.Logger) -> bool:
    global _faiss_gpu_checked, _faiss_gpu_ready
    if _faiss_gpu_checked:
        return _faiss_gpu_ready
    _faiss_gpu_checked = True
    try:
        faiss = _load_faiss()
        import numpy as np
    except Exception as exc:
        logger.warning("faiss gpu unavailable: %s", exc)
        _faiss_gpu_ready = False
        return False

    num_gpus = 0
    if hasattr(faiss, "get_num_gpus"):
        num_gpus = int(faiss.get_num_gpus())

    if num_gpus <= gpu_id:
        logger.warning(
            "faiss gpu disabled requested gpu_id=%s available=%s action=cpu",
            gpu_id,
            num_gpus,
        )
        _faiss_gpu_ready = False
        return False

    try:
        resources = faiss.StandardGpuResources()
        index = faiss.IndexFlatL2(4)
        gpu_index = faiss.index_cpu_to_gpu(resources, gpu_id, index)
        sample = np.zeros((1, 4), dtype="float32")
        gpu_index.add(sample)
        _faiss_gpu_ready = True
        return True
    except Exception as exc:
        logger.warning("faiss gpu init failed for gpu_id=%s: %s", gpu_id, exc)
        _faiss_gpu_ready = False
        return False


def initialize_runtime(
    *,
    cpu_threads: int = _DEFAULT_THREADS,
    use_gpu: bool = True,
    gpu_id: int = _DEFAULT_GPU_ID,
    logger: logging.Logger | None = None,
) -> bool:
    global _runtime_initialized
    configure_logging()
    logger = logger or logging.getLogger("eidolon_v16.runtime")

    with _runtime_lock:
        if not _runtime_initialized:
            configure_threads(cpu_threads)
            _runtime_initialized = True

    gpu_ready = False
    if use_gpu:
        gpu_ready = init_faiss_gpu(gpu_id, logger)
    logger.info("faiss gpu enabled gpu number %s: %s", gpu_id, gpu_ready)
    logger.info("cpu threads set to %s", cpu_threads)
    return gpu_ready
