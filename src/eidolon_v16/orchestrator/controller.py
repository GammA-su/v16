from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from eidolon_v16.arith_types import canonicalize_number
from eidolon_v16.artifacts.manifest import build_artifact_manifest
from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps.dsl import program_from_dict
from eidolon_v16.bvps.interpreter import Interpreter
from eidolon_v16.capsules.bundle import build_capsule
from eidolon_v16.config import AppConfig
from eidolon_v16.kernel.base import Kernel, SolutionCandidate
from eidolon_v16.kernel.http import HttpKernel
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.kernels import resolve_kernel_name
from eidolon_v16.kernels.llamacpp_kernel import from_env as llamacpp_from_env
from eidolon_v16.ledger import chain as ledger_chain
from eidolon_v16.ledger.db import Ledger
from eidolon_v16.orchestrator.types import EpisodeResult, ModeConfig
from eidolon_v16.runtime import initialize_runtime
from eidolon_v16.ucr.canonical import canonical_json_bytes, compute_ucr_hash
from eidolon_v16.ucr.models import UCR, Budget, Decision, HashCommitments, TaskInput, WitnessPacket
from eidolon_v16.utils import safe_eval_arith
from eidolon_v16.verify.lanes import run_anchors, run_consequence, run_recompute, run_translation
from eidolon_v16.worldlab.gridworld import GridWorld
from eidolon_v16.worldlab.runner import run_rollout

logger = logging.getLogger(__name__)


class EpisodeController:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(self, task: TaskInput, mode: ModeConfig) -> EpisodeResult:
        initialize_runtime(
            cpu_threads=mode.cpu_threads,
            use_gpu=mode.use_gpu,
            gpu_id=mode.gpu_id,
            logger=logger,
        )
        store = ArtifactStore(self.config.paths.artifact_store)
        ledger = Ledger(self.config.paths.ledger_db)
        episode_id = self._episode_id(task, mode)
        logger.info("episode start id=%s kind=%s", episode_id, task.normalized.get("kind"))

        kernel = self._select_kernel(store)
        kernel_info = getattr(self, "_kernel_info", {"kind": "unknown"})

        logger.info("interpret phase")
        interpretations = kernel.propose_interpretations(task, seed=mode.seed)
        interpretations.sort(key=lambda item: item.interpretation_id)
        chosen = interpretations[0]

        logger.info("solve phase")
        solution = self._solve_task(task, chosen, kernel, seed=mode.seed)
        solution_payload = self._build_solution_payload(task, solution)
        solution_ref = store.put_json(
            solution_payload, artifact_type="solution", producer="orchestrator"
        )

        logger.info("verify phase")
        lanes = [
            run_recompute(task, solution_payload, store),
            run_translation(task, chosen, solution_payload, store, seed=mode.seed),
            run_consequence(task, solution_payload, store, seed=mode.seed),
        ]
        anchors = run_anchors(lanes, store)
        lanes.append(anchors)

        logger.info("decide phase")
        decision = self._decide(lanes, mode)
        final_result = self._final_result(task, solution_payload, decision)

        logger.info("capsule phase")
        capsule_ref = build_capsule(
            store=store,
            episode_id=episode_id,
            task=task,
            interpretation=chosen,
            solution=solution_payload,
            lanes=lanes,
            decision=decision,
        )

        budgets = Budget(steps=self._budget_steps(solution_payload), cpu_ms=0)

        witness_packet = WitnessPacket(
            episode_id=episode_id,
            final_response=final_result,
            interpretations=interpretations,
            chosen_interpretation_id=chosen.interpretation_id,
            artifact_refs=[solution_ref, capsule_ref],
            verification=lanes,
            budgets=budgets,
            replay=[
                f"uv run eidolon episode replay --ucr runs/{episode_id}/ucr.json",
                "UCR hash: see hashes.ucr_hash in the UCR",
            ],
        )
        witness_ref = store.put_json(
            witness_packet.model_dump(mode="json"),
            artifact_type="witness_packet",
            producer="orchestrator",
        )

        manifest_hash = store.load_manifest().root_hash(exclude_types={"ucr"})

        run_dir = self._run_dir(episode_id)
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact_refs = self._collect_artifact_refs(lanes, [solution_ref, capsule_ref, witness_ref])
        self._write_run_artifacts(store, artifacts_dir, artifact_refs)
        artifact_manifest = build_artifact_manifest(artifacts_dir)

        lane_verdicts = self._build_lane_verdicts(lanes)
        ts_utc = self._utc_now()
        task_text = str(task.normalized.get("prompt", ""))
        solution_summary = {
            "solution_kind": solution_payload.get("solution_kind"),
            "output": solution_payload.get("output"),
        }

        ucr_payload = UCR(
            episode_id=episode_id,
            schema_version="ucr/v1",
            ts_utc=ts_utc,
            task_text=task_text,
            task_input=task,
            interpretations=interpretations,
            chosen_interpretation_id=chosen.interpretation_id,
            budgets=budgets,
            kernel=kernel_info,
            solution=solution_summary,
            lane_verdicts=lane_verdicts,
            costs={},
            artifact_manifest=artifact_manifest,
            decision=decision,
            solution_artifacts=[solution_ref],
            verification=lanes,
            final_result=final_result,
            hashes=HashCommitments(ucr_hash="", artifact_manifest_hash=manifest_hash),
            witness_packet=witness_ref,
        )
        ucr_dict = ucr_payload.model_dump(mode="json")
        ucr_hash = compute_ucr_hash(ucr_dict)
        ucr_payload.hashes.ucr_hash = ucr_hash
        ucr_payload.ucr_hash = ucr_hash
        ucr_dict = ucr_payload.model_dump(mode="json")

        ucr_ref = store.put_json(ucr_dict, artifact_type="ucr", producer="orchestrator")

        ucr_path = run_dir / "ucr.json"
        witness_path = run_dir / "witness.json"
        ucr_path.write_bytes(canonical_json_bytes(ucr_dict))
        witness_payload = witness_packet.model_dump(mode="json")
        witness_payload["ucr_hash"] = ucr_hash
        witness_path.write_bytes(canonical_json_bytes(witness_payload))

        ledger.append_event(
            "ucr",
            {
                "episode_id": episode_id,
                "ucr_hash": ucr_hash,
                "ucr_artifact": ucr_ref.hash,
                "manifest_hash": manifest_hash,
                "run_dir": str(run_dir),
            },
        )
        ledger_chain.append_event(
            self.config.paths.ledger_chain,
            "ucr",
            {"episode_id": episode_id, "ucr_hash": ucr_hash, "run_dir": str(run_dir)},
        )

        logger.info("episode complete id=%s ucr=%s", episode_id, ucr_path)
        return EpisodeResult(ucr_path=ucr_path, witness_path=witness_path, ucr_hash=ucr_hash)

    def replay(self, ucr_path: Path) -> bool:
        initialize_runtime(logger=logger, use_gpu=False)
        logger.info("replay start ucr=%s", ucr_path)
        payload = json.loads(ucr_path.read_text())
        stored_hash = payload.get("hashes", {}).get("ucr_hash", "")
        computed_hash = compute_ucr_hash(payload)
        if stored_hash != computed_hash:
            logger.warning("replay hash mismatch")
            return False
        task = TaskInput.model_validate(payload["task_input"])
        solution_refs = payload.get("solution_artifacts", [])
        if not solution_refs:
            logger.warning("replay missing solution artifacts")
            return False
        store = ArtifactStore(self.config.paths.artifact_store)
        solution_hash = str(solution_refs[0].get("hash", ""))
        if not solution_hash:
            logger.warning("replay missing solution hash")
            return False
        solution_payload = store.read_json_by_hash(solution_hash)
        ok = self._recompute_check(task, solution_payload)
        logger.info("replay complete ok=%s", ok)
        return ok

    def _recompute_check(self, task: TaskInput, solution: dict[str, Any]) -> bool:
        kind = task.normalized.get("kind", "unknown")
        if kind == "arith":
            expr = str(task.normalized.get("data", {}).get("expression", "0"))
            expected = cast(object, solution.get("output"))
            computed = safe_eval_arith(expr)
            try:
                computed_value = canonicalize_number(computed)
                expected_value = canonicalize_number(expected)
            except TypeError:
                return False
            return computed_value == expected_value
        if kind == "list":
            program = program_from_dict(solution["program"])
            interpreter = Interpreter(step_limit=2000)
            output, _trace = interpreter.run(program, [solution["input"]])
            output_value = cast(object, output)
            list_expected = cast(object, solution.get("output"))
            return output_value == list_expected
        if kind == "world":
            actions = solution.get("actions", [])
            world = GridWorld(width=3, height=3, goal=(2, 2))
            rollout = run_rollout(world, actions, seed=0)
            return bool(rollout.get("done"))
        return False

    def _episode_id(self, task: TaskInput, mode: ModeConfig) -> str:
        payload = {"task": task.normalized, "seed": mode.seed}
        digest = compute_ucr_hash({"hashes": {"ucr_hash": ""}, "payload": payload})
        return f"ep-{digest[:12]}"

    def _select_kernel(self, store: ArtifactStore) -> Kernel:
        kernel_value = (os.getenv("EIDOLON_KERNEL") or "").strip()
        if not kernel_value:
            gguf_value = os.getenv("EIDOLON_GGUF", "").strip()
            kernel_kind = "llamacpp" if gguf_value else "stub"
        else:
            kernel_kind = resolve_kernel_name(kernel_value)
        if kernel_kind == "http":
            base_url = os.getenv("EIDOLON_KERNEL_URL", "").strip()
            if not base_url:
                raise ValueError("EIDOLON_KERNEL_URL is required for http kernel")
            self._kernel_info = {"kind": "http", "base_url": base_url}
            logger.info("kernel selected http url=%s", base_url)
            return HttpKernel(base_url=base_url, store=store)
        if kernel_kind == "llamacpp":
            kernel = llamacpp_from_env()
            config = getattr(kernel, "config", None)
            if config is None:
                self._kernel_info = {"kind": "llamacpp"}
            else:
                self._kernel_info = {
                    "kind": "llamacpp",
                    "gguf": config.gguf_path,
                    "n_ctx": config.n_ctx,
                    "n_gpu_layers": config.n_gpu_layers,
                    "n_threads": config.n_threads,
                    "n_batch": config.n_batch,
                    "temperature": config.temperature,
                    "chat_format": config.chat_format,
                }
            logger.info("kernel selected llamacpp")
            return kernel
        if kernel_kind == "unknown":
            logger.warning("unknown EIDOLON_KERNEL=%s; defaulting to stub", kernel_value)
        self._kernel_info = {"kind": "stub"}
        logger.info("kernel selected stub")
        return StubKernel()

    def _solve_task(
        self,
        task: TaskInput,
        interpretation: Any,
        kernel: Kernel,
        *,
        seed: int,
    ) -> SolutionCandidate:
        normalized = task.normalized
        kind = normalized.get("kind", "unknown")
        data = normalized.get("data", {})
        if kind == "arith":
            expr = str(data.get("expression", "")).strip()
            if expr:
                value = canonicalize_number(safe_eval_arith(expr))
                return SolutionCandidate(output=value, solution_kind="arith_eval")
        return kernel.propose_solution(task, interpretation, seed=seed)

    def _build_solution_payload(self, task: TaskInput, solution: Any) -> dict[str, Any]:
        kind = task.normalized.get("kind", "unknown")
        data = task.normalized.get("data", {})
        output_value = solution.output
        if kind == "arith":
            try:
                output_value = canonicalize_number(output_value)
            except TypeError as exc:
                raise ValueError("arith output must be numeric") from exc
        payload: dict[str, Any] = {
            "solution_kind": solution.solution_kind,
            "output": output_value,
        }
        if kind == "arith":
            payload["expression"] = data.get("expression")
        if kind == "list":
            payload["program"] = solution.program
            payload["input"] = data.get("input", [])
            payload["examples"] = data.get("examples", [])
        if kind == "world":
            payload["actions"] = solution.output
            payload["world"] = {"width": 3, "height": 3, "goal": [2, 2]}
        if solution.trace is not None:
            payload["trace"] = solution.trace
        return payload

    def _decide(self, lanes: list[Any], mode: ModeConfig) -> Decision:
        required = set(mode.required_lanes)
        failures = [lane for lane in lanes if lane.lane in required and lane.status != "PASS"]
        if failures:
            rationale = "Required lanes failed: " + ", ".join(lane.lane for lane in failures)
            return Decision(action="refuse", rationale=rationale)
        return Decision(action="answer", rationale="All required lanes passed")

    def _final_result(self, task: TaskInput, solution: dict[str, Any], decision: Decision) -> str:
        if decision.action != "answer":
            return "insufficient verification; refusing"
        return f"result={solution.get('output')}"

    def _budget_steps(self, solution: dict[str, Any]) -> int:
        trace = solution.get("trace", {})
        if isinstance(trace, dict):
            return int(trace.get("steps", 0))
        return 0

    def _run_dir(self, episode_id: str) -> Path:
        run_dir = self.config.paths.runs_dir / episode_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _build_lane_verdicts(self, lanes: list[Any]) -> dict[str, Any]:
        verdicts: dict[str, Any] = {}
        for lane in lanes:
            verdicts[lane.lane] = {
                "status": lane.status,
                "evidence": [ref.model_dump(mode="json") for ref in lane.evidence],
                "notes": lane.notes,
            }
        return verdicts

    def _collect_artifact_refs(self, lanes: list[Any], refs: list[Any]) -> list[Any]:
        seen: set[str] = set()
        collected: list[Any] = []
        for ref in refs:
            if ref.hash in seen:
                continue
            seen.add(ref.hash)
            collected.append(ref)
        for lane in lanes:
            for ref in lane.evidence:
                if ref.hash in seen:
                    continue
                seen.add(ref.hash)
                collected.append(ref)
        return sorted(collected, key=lambda ref: (ref.type, ref.hash))

    def _write_run_artifacts(
        self, store: ArtifactStore, artifacts_dir: Path, refs: list[Any]
    ) -> None:
        for ref in refs:
            ext = self._artifact_extension(ref.media_type)
            filename = f"{ref.type}-{ref.hash}{ext}"
            path = artifacts_dir / filename
            if path.exists():
                continue
            data = store.read_bytes_by_hash(ref.hash)
            path.write_bytes(data)

    def _artifact_extension(self, media_type: str) -> str:
        if media_type == "application/json":
            return ".json"
        if media_type == "application/x-tar":
            return ".tar"
        if media_type.startswith("text/"):
            return ".txt"
        return ".bin"
