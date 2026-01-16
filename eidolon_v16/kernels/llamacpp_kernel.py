from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

from llama_cpp import Llama


@dataclass(frozen=True)
class LlamaCppKernelConfig:
    model_path: str
    n_ctx: int = 4096
    n_gpu_layers: int = 0
    n_threads: int = 0  # 0 = auto
    n_batch: int = 512
    temperature: float = 0.0


class LlamaCppKernel:
    def __init__(self, cfg: LlamaCppKernelConfig) -> None:
        self.cfg = cfg
        self.llm = Llama(
            model_path=cfg.model_path,
            n_ctx=cfg.n_ctx,
            n_gpu_layers=cfg.n_gpu_layers,
            n_threads=(cfg.n_threads if cfg.n_threads > 0 else None),
            n_batch=cfg.n_batch,
        )

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        stop: Sequence[str] | None = None,
    ) -> str:
        out = self.llm(
            prompt,
            max_tokens=max_tokens,
            stop=list(stop) if stop else None,
            temperature=self.cfg.temperature,
        )
        return str(out["choices"][0]["text"])


def from_env() -> LlamaCppKernel:
    mp = (os.environ.get("EIDOLON_GGUF") or "").strip()
    if not mp:
        raise RuntimeError("EIDOLON_GGUF is not set (path to .gguf).")

    return LlamaCppKernel(
        LlamaCppKernelConfig(
            model_path=mp,
            n_ctx=int(os.environ.get("EIDOLON_N_CTX", "4096")),
            n_gpu_layers=int(os.environ.get("EIDOLON_N_GPU_LAYERS", "0")),
            n_threads=int(os.environ.get("EIDOLON_N_THREADS", "0")),
            n_batch=int(os.environ.get("EIDOLON_N_BATCH", "512")),
            temperature=float(os.environ.get("EIDOLON_TEMP", "0.0")),
        )
    )
