from __future__ import annotations

import pytest

from eidolon_v16.kernels import llamacpp_kernel


def test_resolve_n_gpu_layers_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_N_GPU_LAYERS", "5")
    n_gpu_layers, reason = llamacpp_kernel._resolve_n_gpu_layers()
    assert n_gpu_layers == 5
    assert reason == "env"


def test_resolve_n_gpu_layers_default_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EIDOLON_N_GPU_LAYERS", raising=False)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setattr(llamacpp_kernel, "_llama_cuda_available", lambda: False)
    n_gpu_layers, reason = llamacpp_kernel._resolve_n_gpu_layers()
    assert n_gpu_layers == 0
    assert reason == "auto_cpu"
