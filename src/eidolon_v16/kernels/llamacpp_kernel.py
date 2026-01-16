from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from eidolon_v16.kernel.base import Kernel, SolutionCandidate
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.ucr.models import Interpretation, TaskInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlamaCppConfig:
    gguf_path: str
    n_ctx: int
    n_gpu_layers: int
    n_threads: int
    n_batch: int
    temperature: float
    chat_format: str | None


class LlamaCppKernel(Kernel):
    def __init__(self, config: LlamaCppConfig) -> None:
        llama, n_gpu_layers = _load_llama(config)
        if n_gpu_layers != config.n_gpu_layers:
            config = replace(config, n_gpu_layers=n_gpu_layers)
        self.config = config
        self._fallback = StubKernel()
        self._llama = llama
        logger.info(
            "llamacpp kernel init gguf=%s n_ctx=%s n_gpu_layers=%s n_threads=%s "
            "n_batch=%s temp=%s chat_format=%s",
            config.gguf_path,
            config.n_ctx,
            config.n_gpu_layers,
            config.n_threads,
            config.n_batch,
            config.temperature,
            config.chat_format,
        )

    def complete(self, prompt: str, max_tokens: int, stop: Sequence[str] | None) -> str:
        logger.info("llamacpp complete start max_tokens=%s", max_tokens)
        response = cast(Any, self._llama(
            prompt,
            max_tokens=max_tokens,
            stop=stop,
            temperature=self.config.temperature,
        ))
        text = _extract_chat_text(response)
        logger.info("llamacpp complete done chars=%s", len(text))
        return text

    def _complete_json(self, prompt: str, max_tokens: int) -> str:
        logger.info("llamacpp json complete start max_tokens=%s", max_tokens)
        text = _chat_complete(self._llama, prompt, max_tokens, self.config.temperature)
        logger.info("llamacpp json complete done chars=%s", len(text))
        return text

    def propose_interpretations(self, task: TaskInput, *, seed: int) -> list[Interpretation]:
        prompt = _interpretation_prompt(task)
        text = self._complete_json(prompt, max_tokens=256)
        data = _safe_json_loads(text)
        items = data.get("interpretations") if isinstance(data, dict) else data
        if not isinstance(items, list):
            logger.error("llamacpp interpretations invalid payload=%s", data)
            raise ValueError("llamacpp interpretations response must be a list")
        try:
            return [Interpretation.model_validate(item) for item in items]
        except (TypeError, ValueError) as exc:
            logger.error("llamacpp interpretations validation failed raw=%s", text)
            raise ValueError("llamacpp interpretations failed validation") from exc

    def propose_solution(
        self, task: TaskInput, interpretation: Interpretation, *, seed: int
    ) -> SolutionCandidate:
        prompt = _solution_prompt(task, interpretation)
        text = self._complete_json(prompt, max_tokens=256)
        data = _safe_json_loads(text)
        if not isinstance(data, dict):
            logger.error("llamacpp solution invalid payload=%s", data)
            raise ValueError("llamacpp solution response must be an object")
        try:
            return SolutionCandidate(
                output=data.get("output"),
                solution_kind=str(data.get("solution_kind", "llamacpp")),
                program=data.get("program"),
                trace=data.get("trace"),
            )
        except (TypeError, ValueError) as exc:
            logger.error("llamacpp solution validation failed raw=%s", text)
            raise ValueError("llamacpp solution failed validation") from exc

    def critique(self, task: TaskInput, solution: SolutionCandidate, *, seed: int) -> str:
        prompt = _critique_prompt(task, solution)
        text = self.complete(prompt, max_tokens=128, stop=["\n\n"])
        return text.strip()


def config_from_env() -> LlamaCppConfig:
    gguf_path = os.getenv("EIDOLON_GGUF", "").strip()
    if not gguf_path:
        raise ValueError("EIDOLON_GGUF is not set")
    chat_format = os.getenv("EIDOLON_CHAT_FORMAT", "").strip() or None
    if chat_format is None and "qwen" in gguf_path.lower():
        chat_format = "chatml"
    n_gpu_layers, reason = _resolve_n_gpu_layers()
    if reason == "env":
        logger.info("llamacpp n_gpu_layers=%s (EIDOLON_N_GPU_LAYERS override)", n_gpu_layers)
    elif reason == "auto_cuda_api":
        logger.info("llamacpp auto-enabled GPU offload (CUDA backend detected)")
    elif reason == "auto_cuda_visible_devices":
        logger.info(
            "llamacpp auto-enabled GPU offload (CUDA_VISIBLE_DEVICES=%s)",
            os.getenv("CUDA_VISIBLE_DEVICES", ""),
        )
    else:
        logger.info("llamacpp GPU offload disabled (no CUDA detected)")
    return LlamaCppConfig(
        gguf_path=gguf_path,
        n_ctx=_get_int_env("EIDOLON_N_CTX", 2048),
        n_gpu_layers=n_gpu_layers,
        n_threads=_get_int_env("EIDOLON_N_THREADS", 16),
        n_batch=_get_int_env("EIDOLON_N_BATCH", 512),
        temperature=_get_float_env("EIDOLON_TEMP", 0.0),
        chat_format=chat_format,
    )


def from_env() -> LlamaCppKernel:
    return LlamaCppKernel(config_from_env())


def _load_llama(config: LlamaCppConfig) -> tuple[Any, int]:
    from llama_cpp import Llama

    try:
        llama = Llama(
            model_path=config.gguf_path,
            n_ctx=config.n_ctx,
            n_gpu_layers=config.n_gpu_layers,
            n_threads=config.n_threads,
            n_batch=config.n_batch,
            chat_format=config.chat_format,
        )
        return llama, config.n_gpu_layers
    except Exception as exc:
        if config.n_gpu_layers != 0 and _is_cuda_unavailable(exc):
            logger.warning(
                "llamacpp GPU offload unavailable; retrying with n_gpu_layers=0 (%s)",
                exc,
            )
            llama = Llama(
                model_path=config.gguf_path,
                n_ctx=config.n_ctx,
                n_gpu_layers=0,
                n_threads=config.n_threads,
                n_batch=config.n_batch,
                chat_format=config.chat_format,
            )
            return llama, 0
        raise


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an int") from exc


def _get_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float") from exc


def _resolve_n_gpu_layers() -> tuple[int, str]:
    raw = os.getenv("EIDOLON_N_GPU_LAYERS")
    if raw is not None and raw.strip() != "":
        try:
            return int(raw), "env"
        except ValueError as exc:
            raise ValueError("EIDOLON_N_GPU_LAYERS must be an int") from exc
    if _llama_cuda_available():
        return -1, "auto_cuda_api"
    if _cuda_visible_devices_available():
        return -1, "auto_cuda_visible_devices"
    return 0, "auto_cpu"


def _llama_cuda_available() -> bool:
    try:
        import llama_cpp
    except Exception:
        return False
    llama_lib = getattr(llama_cpp, "llama_cpp", None)
    if llama_lib is None:
        return False
    for name in ("llama_supports_gpu_offload", "llama_supports_gpu", "llama_supports_cublas"):
        func = getattr(llama_lib, name, None)
        if callable(func):
            try:
                return bool(func())
            except Exception:
                return False
    return False


def _cuda_visible_devices_available() -> bool:
    raw = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
    return bool(raw) and raw != "-1"


def _is_cuda_unavailable(exc: Exception) -> bool:
    message = str(exc).lower()
    indicators = (
        "no cuda",
        "cuda backend",
        "cublas",
        "ggml_cuda",
        "compiled without",
        "gpu backend",
        "gpu offload",
    )
    return any(indicator in message for indicator in indicators)


def _chat_complete(llama: Any, prompt: str, max_tokens: int, temperature: float) -> str:
    if hasattr(llama, "create_chat_completion"):
        try:
            response = llama.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except (TypeError, ValueError):
            response = llama.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return _extract_chat_text(response)
    response = llama(
        prompt,
        max_tokens=max_tokens,
        stop=None,
        temperature=temperature,
    )
    return _extract_chat_text(response)


def _extract_chat_text(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict) and "content" in message:
                    return str(message["content"])
                if "text" in choice:
                    return str(choice["text"])
    return str(response)


def _safe_json_loads(text: str) -> Any:
    payload = text.lstrip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        decoder = json.JSONDecoder()
        try:
            value, idx = decoder.raw_decode(payload)
            if payload[idx:].strip() == "":
                return value
        except json.JSONDecodeError:
            pass
        extracted = _extract_json(payload)
        if extracted is not None:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
        logger.error("llamacpp json parse failed raw=%s", text)
        raise ValueError("llamacpp returned invalid JSON") from exc


def _extract_json(text: str) -> str | None:
    for start, end in (("[", "]"), ("{", "}")):
        start_idx = text.find(start)
        end_idx = text.rfind(end)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx : end_idx + 1]
    return None


def _interpretation_prompt(task: TaskInput) -> str:
    payload = json.dumps(task.model_dump(mode="json"), ensure_ascii=False)
    return "\n".join(
        [
            "You are an EIDOLON kernel. Return a JSON object with interpretations.",
            "Schema: {\"interpretations\": [{\"interpretation_id\": str, \"description\": str,",
            "          \"assumptions\": [str], \"ambiguity_slots\": []}]}",
            f"Task: {payload}",
            "Return JSON only.",
        ]
    )


def _solution_prompt(task: TaskInput, interpretation: Interpretation) -> str:
    task_payload = json.dumps(task.model_dump(mode="json"), ensure_ascii=False)
    interp_payload = json.dumps(interpretation.model_dump(mode="json"), ensure_ascii=False)
    return "\n".join(
        [
            "You are an EIDOLON kernel. Return a JSON object with solution_kind and output.",
            (
                "Schema: {\"solution_kind\": str, \"output\": any, "
                "\"program\": object?, \"trace\": object?}"
            ),
            f"Task: {task_payload}",
            f"Interpretation: {interp_payload}",
            "Return JSON only.",
        ]
    )


def _critique_prompt(task: TaskInput, solution: SolutionCandidate) -> str:
    task_payload = json.dumps(task.model_dump(mode="json"), ensure_ascii=False)
    solution_payload = json.dumps(
        {"solution_kind": solution.solution_kind, "output": solution.output},
        ensure_ascii=False,
    )
    return "\n".join(
        [
            "Provide a brief critique of the solution.",
            f"Task: {task_payload}",
            f"Solution: {solution_payload}",
        ]
    )
