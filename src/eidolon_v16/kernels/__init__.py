from __future__ import annotations

from typing import Literal

KernelName = Literal["stub", "http", "llamacpp", "unknown"]


def resolve_kernel_name(value: str | None) -> KernelName:
    if value is None:
        return "stub"
    normalized = value.strip().lower()
    if normalized in {"", "stub"}:
        return "stub"
    if normalized == "http":
        return "http"
    if normalized in {"llamacpp", "llama.cpp", "llama-cpp", "llama_cpp"}:
        return "llamacpp"
    return "unknown"
