from __future__ import annotations

import os

from eidolon_v16.kernels import resolve_kernel_name
from eidolon_v16.kernels.llamacpp_kernel import config_from_env


def main() -> int:
    raw = os.getenv("EIDOLON_KERNEL")
    resolved = resolve_kernel_name(raw)
    print(f"resolved_kernel={resolved}")
    if resolved == "llamacpp":
        cfg = config_from_env()
        print(
            "llamacpp_config "
            f"gguf={cfg.gguf_path} n_ctx={cfg.n_ctx} n_gpu_layers={cfg.n_gpu_layers} "
            f"n_threads={cfg.n_threads} n_batch={cfg.n_batch} temp={cfg.temperature}"
        )
        return 0
    if resolved == "unknown":
        print(f"unknown kernel value: {raw}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
