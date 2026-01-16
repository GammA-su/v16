from __future__ import annotations

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.config import default_config
from eidolon_v16.kernels import resolve_kernel_name
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.kernels.llamacpp_kernel import from_env
from eidolon_v16.orchestrator import controller as controller_module
from eidolon_v16.orchestrator.controller import EpisodeController


def test_resolve_kernel_name() -> None:
    assert resolve_kernel_name(None) == "stub"
    assert resolve_kernel_name("") == "stub"
    assert resolve_kernel_name("stub") == "stub"
    assert resolve_kernel_name("http") == "http"
    assert resolve_kernel_name("llamacpp") == "llamacpp"
    assert resolve_kernel_name("llama.cpp") == "llamacpp"
    assert resolve_kernel_name("llama-cpp") == "llamacpp"
    assert resolve_kernel_name("llama_cpp") == "llamacpp"
    assert resolve_kernel_name("unknown-kernel") == "unknown"


def test_llamacpp_requires_gguf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EIDOLON_GGUF", raising=False)
    with pytest.raises(ValueError, match="EIDOLON_GGUF is not set"):
        from_env()


def test_select_kernel_prefers_gguf(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "   ")
    monkeypatch.setenv("EIDOLON_GGUF", str(tmp_path / "model.gguf"))
    sentinel = object()

    def fake_llamacpp_from_env() -> object:
        return sentinel

    monkeypatch.setattr(controller_module, "llamacpp_from_env", fake_llamacpp_from_env)

    config = default_config(tmp_path)
    controller = EpisodeController(config)
    store = ArtifactStore(config.paths.artifact_store)
    kernel = controller._select_kernel(store)
    assert kernel is sentinel


def test_select_kernel_explicit_stub(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "stub")
    monkeypatch.setenv("EIDOLON_GGUF", str(tmp_path / "model.gguf"))
    config = default_config(tmp_path)
    controller = EpisodeController(config)
    store = ArtifactStore(config.paths.artifact_store)
    kernel = controller._select_kernel(store)
    assert isinstance(kernel, StubKernel)


def test_select_kernel_unknown_value(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EIDOLON_KERNEL", "unknown-kernel")
    monkeypatch.setenv("EIDOLON_GGUF", str(tmp_path / "model.gguf"))
    config = default_config(tmp_path)
    controller = EpisodeController(config)
    store = ArtifactStore(config.paths.artifact_store)
    kernel = controller._select_kernel(store)
    assert isinstance(kernel, StubKernel)
