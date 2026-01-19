from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from eidolon_v16.arith_types import canonicalize_number
from eidolon_v16.artifacts.manifest import build_artifact_manifest
from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import ast as bvps_ast
from eidolon_v16.bvps import cegis as bvps_cegis
from eidolon_v16.bvps import types as bvps_types
from eidolon_v16.bvps.dsl import program_from_dict
from eidolon_v16.bvps.interpreter import Interpreter
from eidolon_v16.capsules.bundle import build_capsule
from eidolon_v16.config import AppConfig
from eidolon_v16.kernel.base import Kernel, SolutionCandidate
from eidolon_v16.kernel.http import HttpKernel
from eidolon_v16.kernel.stub import StubKernel
from eidolon_v16.kernels import resolve_kernel_name
from eidolon_v16.kernels.llamacpp_kernel import from_env as llamacpp_from_env
from eidolon_v16.language.registry import load_registry as load_language_registry
from eidolon_v16.language.spec import MacroTemplate
from eidolon_v16.ledger import chain as ledger_chain
from eidolon_v16.ledger.db import Ledger
from eidolon_v16.orchestrator.types import EpisodeResult, ModeConfig
from eidolon_v16.runtime import initialize_runtime
from eidolon_v16.skills.admission import admit_skill
from eidolon_v16.skills.bundle import bundle_identity, write_skill_bundle
from eidolon_v16.skills.compile import compile_skill_from_bvps
from eidolon_v16.skills.registry import load_registry as load_skill_registry
from eidolon_v16.skills.registry import register_skill
from eidolon_v16.skills.store import load_bundle, save_bundle
from eidolon_v16.ucr.canonical import canonical_json_bytes, compute_ucr_hash
from eidolon_v16.ucr.models import (
    UCR,
    Budget,
    Decision,
    HashCommitments,
    Interpretation,
    TaskInput,
    WitnessPacket,
)
from eidolon_v16.utils import safe_eval_arith
from eidolon_v16.verify.lanes import run_consequence, run_lanes, run_translation
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

        bvps_spec = self._parse_bvps_spec(task)
        extra_artifact_refs: list[Any] = []
        skill_artifact_refs: list[Any] = []
        bvps_summary: dict[str, Any] | None = None
        used_skill: dict[str, Any] | None = None
        admitted_skill: dict[str, Any] | None = None
        active_language_patches: list[dict[str, Any]] = []
        macros_for_spec: dict[str, MacroTemplate] = {}
        overall_start = time.perf_counter()
        phase_ms: dict[str, int] = {}
        solve_duration_ms = 0
        if bvps_spec is not None:
            self._inject_bvps_spec(task, bvps_spec)
            kernel_info = {"kind": "bvps"}
            logger.info("interpret phase (bvps)")
            interpret_start = time.perf_counter()
            interpretations = self._bvps_interpretations(bvps_spec)
            chosen = interpretations[0]
            phase_ms["interpret"] = int((time.perf_counter() - interpret_start) * 1000)
            logger.info("solve phase (bvps)")
            solve_start = time.perf_counter()
            macros_for_spec, active_language_patches = self._load_language_macros(bvps_spec)
            skill_match = self._try_skill_for_bvps(task, store)
            if skill_match is None:
                solution, extra_artifact_refs, bvps_summary = self._solve_bvps(
                    task,
                    bvps_spec,
                    store,
                    seed=mode.seed,
                    episode_id=episode_id,
                    macros=macros_for_spec,
                )
            else:
                solution = skill_match["solution"]
                skill_artifact_refs.extend(skill_match["artifact_refs"])
                used_skill = skill_match["used_skill"]
                bvps_summary = skill_match["summary"]
            solve_duration_ms = int((time.perf_counter() - solve_start) * 1000)
            phase_ms["solve"] = solve_duration_ms
        else:
            kernel = self._select_kernel(store)
            kernel_info = getattr(self, "_kernel_info", {"kind": "unknown"})
            logger.info("interpret phase")
            interpret_start = time.perf_counter()
            interpretations = kernel.propose_interpretations(task, seed=mode.seed)
            interpretations.sort(key=lambda item: item.interpretation_id)
            chosen = interpretations[0]
            phase_ms["interpret"] = int((time.perf_counter() - interpret_start) * 1000)

            logger.info("solve phase")
            solve_start = time.perf_counter()
            solution = self._solve_task(task, chosen, kernel, seed=mode.seed)
            solve_duration_ms = int((time.perf_counter() - solve_start) * 1000)
            phase_ms["solve"] = solve_duration_ms
        solution_payload = self._build_solution_payload(task, solution)
        solution_ref = store.put_json(
            solution_payload, artifact_type="solution", producer="orchestrator"
        )

        logger.info("verify phase")
        verify_start = time.perf_counter()
        verify_artifact_ms = 0
        lanes, lane_durations, verify_artifact_ms = run_lanes(
            task,
            chosen,
            solution_payload,
            store,
            seed=mode.seed,
        )
        recompute, translation, consequence, anchors = lanes
        self._maybe_bvps_autorepair(
            task=task,
            chosen=chosen,
            solution_payload=solution_payload,
            store=store,
            lanes=lanes,
            seed=mode.seed,
            episode_id=episode_id,
        )
        verify_admission_ms = 0
        skill_result = None
        if self._auto_skills_enabled():
            admission_start = time.perf_counter()
            skill_result = self._maybe_auto_skill(
                task=task,
                solution_payload=solution_payload,
                lanes=lanes,
                store=store,
                seed=mode.seed,
                episode_id=episode_id,
                used_skill=used_skill,
            )
            verify_admission_ms = int(round((time.perf_counter() - admission_start) * 1000))
            if verify_admission_ms < 0:
                verify_admission_ms = 0
        if skill_result is not None:
            bundle = skill_result["bundle"]
            skill_artifact_refs.extend(bundle.artifact_refs)
            admission_ref = skill_result["admission_ref"]
            if admission_ref is not None:
                skill_artifact_refs.append(admission_ref)
            if skill_result["admitted"]:
                admission_path = skill_result.get(
                    "existing_admission_path",
                    f"skills/{bundle.spec.name}/admission_verdict.json",
                )
                admitted_skill = {
                    "name": bundle.spec.name,
                    "version": bundle.spec.version,
                    "admission_path": admission_path,
                    "bundle_path": f"skills/{bundle.spec.name}",
                }
        phase_ms["verify"] = int((time.perf_counter() - verify_start) * 1000)
        verify_lane_exec_ms = sum(int(value) for value in lane_durations.values())
        verify_overhead_ms = phase_ms["verify"] - (
            verify_lane_exec_ms + verify_artifact_ms + verify_admission_ms
        )
        if verify_overhead_ms < 0:
            verify_overhead_ms = 0
        verify_breakdown_ms = {
            "verify_lane_exec_ms": verify_lane_exec_ms,
            "verify_artifact_ms": verify_artifact_ms,
            "verify_admission_ms": verify_admission_ms,
            "verify_overhead_ms": verify_overhead_ms,
        }
        logger.info("decide phase")
        decide_start = time.perf_counter()
        decision = self._decide(lanes, mode)
        final_result = self._final_result(task, solution_payload, decision)
        phase_ms["decide"] = int((time.perf_counter() - decide_start) * 1000)

        logger.info("capsule phase")
        capsule_start = time.perf_counter()
        capsule_ref = build_capsule(
            store=store,
            episode_id=episode_id,
            task=task,
            interpretation=chosen,
            solution=solution_payload,
            lanes=lanes,
            decision=decision,
        )
        phase_ms["capsule"] = int((time.perf_counter() - capsule_start) * 1000)

        budgets = Budget(steps=self._budget_steps(solution_payload), cpu_ms=0)

        run_dir = self._run_dir(episode_id)

        lane_durations = dict(lane_durations)
        total_ms = int((time.perf_counter() - overall_start) * 1000)
        witness_costs = {
            "phase_ms": phase_ms,
            "total_ms": total_ms,
            "lane_ms": lane_durations,
            "verify_breakdown_ms": verify_breakdown_ms,
        }

        witness_packet = WitnessPacket(
            episode_id=episode_id,
            final_response=final_result,
            interpretations=interpretations,
            chosen_interpretation_id=chosen.interpretation_id,
            artifact_refs=[solution_ref, capsule_ref],
            verification=lanes,
            budgets=budgets,
            replay=[
                f"uv run eidolon episode replay --ucr {run_dir / 'ucr.json'}",
                "UCR hash: see hashes.ucr_hash in the UCR",
            ],
            costs=witness_costs,
            used_skill=used_skill,
            admitted_skill=admitted_skill,
            active_language_patches=active_language_patches,
            run_dir=str(run_dir),
        )
        witness_ref = store.put_json(
            witness_packet.model_dump(mode="json"),
            artifact_type="witness_packet",
            producer="orchestrator",
        )

        manifest_hash = store.load_manifest().root_hash(exclude_types={"ucr"})

        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact_refs = self._collect_artifact_refs(
            lanes,
            [solution_ref, capsule_ref, witness_ref],
            extra_artifact_refs + skill_artifact_refs,
        )
        written_paths = self._write_run_artifacts(store, artifacts_dir, artifact_refs)
        artifact_manifest = build_artifact_manifest(artifacts_dir)

        artifact_bytes = sum(entry.get("bytes", 0) for entry in artifact_manifest)
        costs: dict[str, Any] = {
            "solve_wall_ms": solve_duration_ms,
            "verifier_ms": lane_durations,
            "lane_ms": lane_durations,
            "phase_ms": phase_ms,
            "verify_breakdown_ms": verify_breakdown_ms,
            "total_ms": total_ms,
            "artifact_bytes": artifact_bytes,
        }
        if bvps_summary is not None:
            stats = bvps_summary.get("stats", {})
            if isinstance(stats, dict):
                for key in ("candidates_tried", "counterexamples", "fuzz_trials"):
                    value = stats.get(key)
                    if value is not None:
                        costs[f"bvps_{key}"] = value

        lane_verdicts = self._build_lane_verdicts(lanes)
        ts_utc = self._utc_now()
        task_text = str(task.normalized.get("prompt", ""))
        solution_summary = bvps_summary or {
            "solution_kind": solution_payload.get("solution_kind"),
            "output": solution_payload.get("output"),
        }

        ucr_payload = UCR(
            episode_id=episode_id,
            schema_version="ucr/v1",
            run_dir=str(run_dir),
            ts_utc=ts_utc,
            task_text=task_text,
            task_input=task,
            interpretations=interpretations,
            chosen_interpretation_id=chosen.interpretation_id,
            budgets=budgets,
            kernel=kernel_info,
            solution=solution_summary,
            lane_verdicts=lane_verdicts,
            costs=costs,
            artifact_manifest=artifact_manifest,
            decision=decision,
            solution_artifacts=[solution_ref],
            verification=lanes,
            final_result=final_result,
            hashes=HashCommitments(ucr_hash="", artifact_manifest_hash=manifest_hash),
            witness_packet=witness_ref,
            used_skill=used_skill,
            admitted_skill=admitted_skill,
            active_language_patches=active_language_patches,
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
        self._inject_witness_paths(witness_payload, artifact_manifest, written_paths)
        witness_payload["ucr_hash"] = ucr_hash
        witness_payload["run_dir"] = str(run_dir)
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
            try:
                computed_value = canonicalize_number(safe_eval_arith(expr))
                expected_value = canonicalize_number(expected)
            except Exception:
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
        data = normalized.setdefault("data", {})
        if kind == "arith":
            expr = self._extract_arith_expression(task)
            if expr:
                data["expression"] = expr
                try:
                    value = canonicalize_number(safe_eval_arith(expr))
                except Exception as exc:
                    return SolutionCandidate(
                        output=None,
                        solution_kind="arith_error",
                        trace={"error": str(exc)},
                    )
                return SolutionCandidate(output=value, solution_kind="arith_eval")
        return kernel.propose_solution(task, interpretation, seed=seed)

    def _extract_arith_expression(self, task: TaskInput) -> str:
        normalized = task.normalized
        data = normalized.get("data", {}) or {}
        expr = str(data.get("expression") or "").strip()
        if expr:
            return expr
        prompt = str(normalized.get("prompt", "")).strip()
        for prefix in ("ARITH:", "arith:"):
            if prompt.startswith(prefix):
                return prompt[len(prefix) :].strip()
        return ""

    def _parse_bvps_spec(self, task: TaskInput) -> dict[str, Any] | None:
        prompt = str(task.normalized.get("prompt", ""))
        if prompt.startswith("BVPS_SPEC:"):
            raw = prompt[len("BVPS_SPEC:") :].strip()
            if raw:
                return cast(dict[str, Any], json.loads(raw))
        if os.getenv("EIDOLON_BVPS", "").strip() == "1":
            data = task.normalized.get("data", {})
            spec = data.get("bvps_spec") or data.get("spec")
            if isinstance(spec, str):
                return cast(dict[str, Any], json.loads(spec))
            if isinstance(spec, dict):
                return cast(dict[str, Any], spec)
        data = task.normalized.get("data", {})
        spec = data.get("bvps_spec")
        if isinstance(spec, dict):
            return cast(dict[str, Any], spec)
        return None

    def _inject_bvps_spec(self, task: TaskInput, spec: dict[str, Any]) -> None:
        task.normalized["kind"] = "bvps"
        data = task.normalized.setdefault("data", {})
        data["bvps_spec"] = spec

    def _bvps_interpretations(self, spec: dict[str, Any]) -> list[Any]:
        name = str(spec.get("name", "bvps"))
        return [
            Interpretation(
                interpretation_id="bvps-spec",
                description=f"BVPS spec {name}",
                assumptions=["Interpret task as BVPS spec synthesis."],
            )
        ]

    def _load_language_macros(
        self, spec_payload: dict[str, Any]
    ) -> tuple[dict[str, MacroTemplate], list[dict[str, Any]]]:
        registry = load_language_registry(self.config.paths.language_registry)
        macros: dict[str, MacroTemplate] = {}
        patches: list[dict[str, Any]] = []
        scope = str(spec_payload.get("name", "")).strip()
        for record in registry.patches:
            if record.spec.scope != scope:
                continue
            macros.update(record.spec.macros)
            patches.append(
                {
                    "name": record.spec.name,
                    "version": record.spec.version,
                    "scope": record.spec.scope,
                }
            )
        return macros, patches

    def _solve_bvps(
        self,
        task: TaskInput,
        spec_payload: dict[str, Any],
        store: ArtifactStore,
        *,
        seed: int,
        episode_id: str,
        macros: dict[str, MacroTemplate],
    ) -> tuple[SolutionCandidate, list[Any], dict[str, Any]]:
        spec = bvps_types.spec_from_dict(spec_payload)
        derived_seed = self._seed_from_episode_id(episode_id)
        result = bvps_cegis.synthesize(spec, seed=derived_seed, macros=macros)
        program_dict = result.program.to_dict()
        program_pretty = bvps_ast.expr_to_str(result.program.body)

        spec_ref = store.put_json(spec_payload, artifact_type="bvps_spec", producer="bvps")
        program_ref = store.put_json(
            program_dict,
            artifact_type="bvps_program",
            producer="bvps",
            created_from=[spec_ref.hash],
        )
        report_payload = {
            "program_pretty": program_pretty,
            "stats": {
                "candidates_tried": result.stats.candidates_tried,
                "depth": result.stats.depth,
                "counterexamples": result.stats.counterexamples,
                "seed": result.stats.seed,
                "fuzz_trials": result.stats.fuzz_trials,
            },
            "examples": [
                {"in": ex.inputs, "out": ex.output} for ex in result.examples
            ],
            "counterexamples": [
                {"in": ex.inputs, "out": ex.output} for ex in result.counterexamples
            ],
        }
        report_ref = store.put_json(
            report_payload,
            artifact_type="bvps_report",
            producer="bvps",
            created_from=[spec_ref.hash, program_ref.hash],
        )

        solution = SolutionCandidate(
            output=None,
            solution_kind="bvps_program",
            program=program_dict,
            trace={"bvps_report": report_ref.hash},
        )
        summary = {
            "solution_kind": "bvps_program",
            "program_pretty": program_pretty,
            "stats": report_payload["stats"],
            "macros": list(macros.keys()),
        }
        return solution, [spec_ref, program_ref, report_ref], summary

    def _try_skill_for_bvps(
        self,
        task: TaskInput,
        store: ArtifactStore,
    ) -> dict[str, Any] | None:
        registry = load_skill_registry(self.config.paths.skills_registry)
        if not registry.skills:
            return None
        data = task.normalized.get("data", {})
        spec_payload = data.get("bvps_spec")
        if not isinstance(spec_payload, dict):
            return None
        spec_name = str(spec_payload.get("name", "")).lower()
        prompt = str(task.normalized.get("prompt", "")).lower()
        records = sorted(registry.skills, key=lambda record: record.spec.name)
        for record in records:
            if not self._skill_matches(record.spec, spec_name, prompt, task.normalized.get("kind")):
                continue
            bundle_dir = Path(record.bundle_dir)
            if not bundle_dir.exists():
                continue
            bundle = load_bundle(bundle_dir)
            identity = bundle_identity(bundle)
            existing_admission = None
            if self._auto_skills_enabled():
                existing_admission = self._load_existing_admission(bundle_dir, identity)
            recorded_bundle = None
            if existing_admission is None:
                recorded_bundle = write_skill_bundle(
                    store=store,
                    skill_spec=bundle.spec,
                    program_ast=bundle.program,
                    tests=bundle.tests,
                    verify_profile=bundle.verify_profile,
                )
            program_pretty = bvps_ast.expr_to_str(
                bvps_ast.program_from_dict(bundle.program).body
            )
            used_skill = {
                "name": bundle.spec.name,
                "version": bundle.spec.version,
                "bundle_dir": record.bundle_dir,
                "bundle_path": f"skills/{bundle.spec.name}",
            }
            summary = {
                "solution_kind": "skill_bvps",
                "program_pretty": program_pretty,
                "used_skill": used_skill,
            }
            solution = SolutionCandidate(
                output=None,
                solution_kind="skill_bvps",
                program=bundle.program,
                trace={"used_skill": used_skill},
            )
            return {
                "solution": solution,
                "artifact_refs": recorded_bundle.artifact_refs if recorded_bundle else [],
                "used_skill": used_skill,
                "summary": summary,
            }
        return None

    def _skill_matches(
        self,
        spec: Any,
        spec_name: str,
        prompt: str,
        task_family: str | None,
    ) -> bool:
        trigger = spec.triggers
        if trigger.task_family and trigger.task_family != task_family:
            return False
        if not trigger.task_contains:
            return False
        haystack = f"{spec_name} {prompt}"
        return any(
            keyword and keyword.lower() in haystack for keyword in trigger.task_contains
        )

    def _build_solution_payload(self, task: TaskInput, solution: Any) -> dict[str, Any]:
        kind = task.normalized.get("kind", "unknown")
        data = task.normalized.get("data", {})
        output_value = solution.output
        if kind == "arith" and solution.solution_kind != "arith_error":
            try:
                output_value = canonicalize_number(output_value)
            except TypeError as exc:
                raise ValueError("arith output must be numeric") from exc
        payload: dict[str, Any] = {
            "solution_kind": solution.solution_kind,
            "output": output_value,
        }
        if solution.trace:
            payload["trace"] = solution.trace
        if kind == "arith":
            payload["expression"] = data.get("expression")
        if kind == "bvps":
            payload["program"] = solution.program
            payload["bvps_spec"] = data.get("bvps_spec")
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
        base = self.config.paths.runs_dir
        base.mkdir(parents=True, exist_ok=True)
        candidate = base / episode_id
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        suffix = 1
        while True:
            candidate = base / f"{episode_id}-r{suffix:02d}"
            if not candidate.exists():
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
            suffix += 1

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _seed_from_episode_id(self, episode_id: str) -> int:
        digest = compute_ucr_hash({"hashes": {"ucr_hash": ""}, "episode_id": episode_id})
        return int(digest[:8], 16)

    def _auto_skills_enabled(self) -> bool:
        return os.getenv("EIDOLON_AUTO_SKILLS", "").strip() == "1"

    def _admission_reverify_enabled(self) -> bool:
        return os.getenv("EIDOLON_ADMISSION_REVERIFY", "").strip() == "1"

    def _admission_path(self, bundle_dir: Path) -> Path:
        candidate = bundle_dir / "admission_verdict.json"
        if candidate.exists():
            return candidate
        return bundle_dir.parent / "admission_verdict.json"

    def _load_existing_admission(
        self, bundle_dir: Path, identity: dict[str, str]
    ) -> dict[str, Any] | None:
        if self._admission_reverify_enabled():
            return None
        path = self._admission_path(bundle_dir)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        admitted = payload.get("admitted")
        if admitted is None:
            status = payload.get("status") or payload.get("rationale")
            admitted = str(status or "").upper() == "PASS"
        if not admitted:
            return None
        bundle_meta = payload.get("bundle")
        if not isinstance(bundle_meta, dict):
            return None
        if bundle_meta.get("name") != identity.get("name"):
            return None
        if bundle_meta.get("version") != identity.get("version"):
            return None
        if bundle_meta.get("spec_hash") != identity.get("spec_hash"):
            return None
        if bundle_meta.get("bundle_hash") != identity.get("bundle_hash"):
            return None
        return {"path": path, "payload": payload}

    def _write_admission_verdict(
        self,
        bundle_dir: Path,
        payload: dict[str, Any],
    ) -> None:
        admission_path = bundle_dir.parent / "admission_verdict.json"
        admission_path.write_bytes(canonical_json_bytes(payload))

    def _build_lane_verdicts(self, lanes: list[Any]) -> dict[str, Any]:
        verdicts: dict[str, Any] = {}
        for lane in lanes:
            verdicts[lane.lane] = {
                "status": lane.status,
                "cost_ms": lane.cost_ms,
                "evidence": [ref.model_dump(mode="json") for ref in lane.evidence],
                "notes": lane.notes,
                "costs": lane.costs,
            }
        return verdicts

    def _collect_artifact_refs(
        self, lanes: list[Any], refs: list[Any], extra_refs: list[Any] | None = None
    ) -> list[Any]:
        seen: set[str] = set()
        collected: list[Any] = []
        for ref in refs:
            if ref.hash in seen:
                continue
            seen.add(ref.hash)
            collected.append(ref)
        for ref in extra_refs or []:
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
    ) -> dict[str, list[str]]:
        written: dict[str, list[str]] = {}
        verify_map = {
            "consequence_bvps": "verify/consequence_bvps.json",
            "consequence_bvps_attempt2": "verify/consequence_bvps_attempt2.json",
            "translation_bvps": "verify/translation_bvps.json",
            "translation_bvps_attempt2": "verify/translation_bvps_attempt2.json",
        }
        skill_map = {
            "skill_spec": "skill.json",
            "skill_program": "program.json",
            "skill_tests": "tests.json",
            "skill_verify_profile": "verify_profile.json",
            "skill_sealed_lite": "sealed_lite.json",
            "skill_admission": "admission_verdict.json",
        }
        for ref in refs:
            ext = self._artifact_extension(ref.media_type)
            data = store.read_bytes_by_hash(ref.hash)
            verify_rel = verify_map.get(ref.type)
            if verify_rel is not None:
                path = artifacts_dir / verify_rel
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(data)
                self._append_written(written, ref.hash, verify_rel)
            else:
                skill_rel = self._skill_artifact_path(ref.type, skill_map)
                if skill_rel is not None:
                    path = artifacts_dir / skill_rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        path.write_bytes(data)
                    self._append_written(written, ref.hash, skill_rel)
                else:
                    filename = f"{ref.type}-{ref.hash}{ext}"
                    subdir = artifacts_dir
                    if ref.type.startswith("bvps_"):
                        subdir = artifacts_dir / "bvps"
                        subdir.mkdir(parents=True, exist_ok=True)
                    path = subdir / filename
                    if not path.exists():
                        path.write_bytes(data)
                    relative = path.relative_to(artifacts_dir).as_posix()
                    self._append_written(written, ref.hash, relative)
            self._ensure_base_artifact(artifacts_dir, ref, ext, data, written)
        return written

    def _artifact_extension(self, media_type: str) -> str:
        if media_type == "application/json":
            return ".json"
        if media_type == "application/x-tar":
            return ".tar"
        if media_type.startswith("text/"):
            return ".txt"
        return ".bin"

    def _skill_artifact_path(self, artifact_type: str, skill_map: dict[str, str]) -> str | None:
        if not artifact_type.startswith("skill_"):
            return None
        if ":" not in artifact_type:
            return None
        kind, name = artifact_type.split(":", 1)
        filename = skill_map.get(kind)
        if filename is None:
            return None
        return f"skills/{name}/{filename}"

    def _append_written(self, written: dict[str, list[str]], ref_hash: str, relpath: str) -> None:
        rel = relpath.replace("\\", "/")
        if rel not in written.setdefault(ref_hash, []):
            written.setdefault(ref_hash, []).append(rel)

    def _ensure_base_artifact(
        self,
        artifacts_dir: Path,
        ref: Any,
        ext: str,
        data: bytes,
        written: dict[str, list[str]],
    ) -> None:
        base_path = artifacts_dir / f"{ref.type}-{ref.hash}{ext}"
        base_path.parent.mkdir(parents=True, exist_ok=True)
        if not base_path.exists():
            base_path.write_bytes(data)
        self._append_written(written, ref.hash, base_path.relative_to(artifacts_dir).as_posix())

    def _maybe_bvps_autorepair(
        self,
        *,
        task: TaskInput,
        chosen: Interpretation,
        solution_payload: dict[str, Any],
        store: ArtifactStore,
        lanes: list[Any],
        seed: int,
        episode_id: str,
    ) -> None:
        if task.normalized.get("kind") != "bvps":
            return
        if os.getenv("EIDOLON_BVPS_AUTOREPAIR", "").strip() != "1":
            return
        consequence_lane = next((lane for lane in lanes if lane.lane == "consequence"), None)
        if consequence_lane is None or consequence_lane.status != "FAIL":
            return
        counterexample = self._extract_bvps_counterexample(store, consequence_lane)
        if counterexample is None or counterexample.get("expected") is None:
            return
        spec_payload = task.normalized.get("data", {}).get("bvps_spec")
        if not isinstance(spec_payload, dict):
            return
        spec = bvps_types.spec_from_dict(spec_payload)
        spec_dict = bvps_types.spec_to_dict(spec)
        spec_dict.setdefault("examples", []).append(
            {"in": counterexample["input"], "out": counterexample["expected"]}
        )
        repaired_spec = bvps_types.spec_from_dict(spec_dict)
        derived_seed = self._seed_from_episode_id(episode_id)
        result = bvps_cegis.synthesize(repaired_spec, seed=derived_seed)
        repaired_solution = dict(solution_payload)
        repaired_solution["program"] = result.program.to_dict()

        translation_attempt = run_translation(
            task, chosen, repaired_solution, store, seed=seed, attempt=2
        )
        consequence_attempt = run_consequence(
            task, repaired_solution, store, seed=seed, attempt=2
        )
        self._append_attempt(lanes, "translation", translation_attempt)
        self._append_attempt(lanes, "consequence", consequence_attempt)

    def _extract_bvps_counterexample(
        self, store: ArtifactStore, lane: Any
    ) -> dict[str, Any] | None:
        for ref in lane.evidence:
            payload = store.read_json_by_hash(ref.hash)
            counterexample = payload.get("counterexample")
            if isinstance(counterexample, dict) and "input" in counterexample:
                return counterexample
        return None

    def _append_attempt(self, lanes: list[Any], lane_name: str, attempt: Any) -> None:
        for lane in lanes:
            if lane.lane != lane_name:
                continue
            lane.evidence.extend(attempt.evidence)
            notes = lane.notes or ""
            suffix = f" attempt2={attempt.status}"
            lane.notes = (notes + suffix).strip()
            break

    def _inject_witness_paths(
        self,
        witness_payload: dict[str, Any],
        artifact_manifest: list[dict[str, Any]],
        written_paths: dict[str, list[str]],
    ) -> None:
        hash_to_paths: dict[str, list[str]] = {}
        for entry in artifact_manifest:
            content_hash = entry.get("sha256")
            if not isinstance(content_hash, str):
                continue
            path = entry.get("path")
            if not isinstance(path, str):
                continue
            hash_to_paths.setdefault(content_hash, []).append(path)
        for content_hash, paths in written_paths.items():
            hash_to_paths.setdefault(content_hash, []).extend(paths)
        for paths in hash_to_paths.values():
            paths.sort()
        for lane in witness_payload.get("verification", []):
            for ref in lane.get("evidence", []):
                content_hash = ref.get("hash")
                if not isinstance(content_hash, str):
                    continue
                paths = hash_to_paths.get(content_hash, [])
                if not paths:
                    continue
                preferred = next((p for p in paths if p.startswith("verify/")), paths[0])
                ref["path"] = preferred

    def _maybe_auto_skill(
        self,
        *,
        task: TaskInput,
        solution_payload: dict[str, Any],
        lanes: list[Any],
        store: ArtifactStore,
        seed: int,
        episode_id: str,
        used_skill: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if task.normalized.get("kind") != "bvps":
            return None
        if not self._auto_skills_enabled():
            return None
        if used_skill is not None:
            bundle_dir_value = used_skill.get("bundle_dir")
            if isinstance(bundle_dir_value, str) and bundle_dir_value:
                bundle_dir = Path(bundle_dir_value)
                if bundle_dir.exists():
                    bundle = load_bundle(bundle_dir)
                    identity = bundle_identity(bundle)
                    existing = self._load_existing_admission(bundle_dir, identity)
                    if existing is not None:
                        return {
                            "bundle": bundle,
                            "admitted": True,
                            "admission_ref": None,
                            "existing_admission_path": str(existing["path"]),
                        }
        bundle = compile_skill_from_bvps(
            task=task,
            solution=solution_payload,
            lanes=lanes,
            store=store,
            episode_id=episode_id,
            seed=seed,
        )
        if bundle is None:
            return None
        admission = admit_skill(bundle=bundle, store=store, seed=seed)
        if admission.admitted:
            bundle_dir = save_bundle(bundle, self.config.paths.skills_dir)
            register_skill(self.config.paths.skills_registry, bundle.spec, bundle_dir)
            if admission.evidence_ref is not None:
                payload = store.read_json_by_hash(admission.evidence_ref.hash)
                if isinstance(payload, dict):
                    self._write_admission_verdict(bundle_dir, payload)
        return {
            "bundle": bundle,
            "admitted": admission.admitted,
            "admission_ref": admission.evidence_ref,
        }
