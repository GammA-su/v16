from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich.console import Console

from eidolon_v16.config import default_config
from eidolon_v16.eval.open_eval import run_open_eval
from eidolon_v16.eval.sealed_eval import run_sealed_eval
from eidolon_v16.ledger.db import Ledger
from eidolon_v16.orchestrator.controller import EpisodeController
from eidolon_v16.orchestrator.types import ModeConfig, TaskInput
from eidolon_v16.runtime import initialize_runtime
from eidolon_v16.skills.registry import SkillRegistry

app = typer.Typer(help="EIDOLON v16 CLI")
episode_app = typer.Typer(help="Episode commands")
eval_app = typer.Typer(help="Evaluation commands")
skills_app = typer.Typer(help="Skills commands")
ledger_app = typer.Typer(help="Ledger commands")

app.add_typer(episode_app, name="episode")
app.add_typer(eval_app, name="eval")
app.add_typer(skills_app, name="skills")
app.add_typer(ledger_app, name="ledger")

console = Console()
logger = logging.getLogger(__name__)

TASK_FILE_OPTION = typer.Option(..., "--task-file", exists=True, dir_okay=False)
SEED_OPTION = typer.Option(0, "--seed")
UCR_OPTION = typer.Option(..., "--ucr", exists=True, dir_okay=False)
N_OPTION = typer.Option(10, "--n")
SUITE_OPTION = typer.Option(..., "--suite", exists=True, dir_okay=False)
SEALED_SEED_OPTION = typer.Option(None, "--seed")
REVEAL_SEED_OPTION = typer.Option(False, "--reveal-seed")


def _load_task(path: Path) -> TaskInput:
    raw = json.loads(path.read_text())
    return TaskInput.from_raw(raw)


@episode_app.command("run")
def episode_run(
    task_file: Path = TASK_FILE_OPTION,
    seed: int = SEED_OPTION,
) -> None:
    mode = ModeConfig(seed=seed)
    initialize_runtime(
        cpu_threads=mode.cpu_threads,
        use_gpu=mode.use_gpu,
        gpu_id=mode.gpu_id,
        logger=logger,
    )
    logger.info("episode run start task=%s seed=%s", task_file, seed)
    config = default_config()
    controller = EpisodeController(config=config)
    task = _load_task(task_file)
    result = controller.run(task=task, mode=mode)
    logger.info("episode run complete ucr=%s", result.ucr_path)
    console.print("Episode complete")
    console.print(f"UCR: {result.ucr_path}")
    console.print(f"Witness: {result.witness_path}")


@episode_app.command("replay")
def episode_replay(ucr: Path = UCR_OPTION) -> None:
    initialize_runtime(logger=logger)
    logger.info("episode replay start ucr=%s", ucr)
    config = default_config()
    controller = EpisodeController(config=config)
    ok = controller.replay(ucr_path=ucr)
    if not ok:
        raise typer.Exit(code=1)
    logger.info("episode replay complete")
    console.print("Replay OK")


@ledger_app.command("verify")
def ledger_verify() -> None:
    initialize_runtime(logger=logger)
    logger.info("ledger verify start")
    config = default_config()
    ledger = Ledger(config.paths.ledger_db)
    ok, message = ledger.verify_chain()
    if not ok:
        console.print(f"Ledger verify FAIL: {message}")
        raise typer.Exit(code=1)
    logger.info("ledger verify pass")
    console.print("Ledger verify PASS")


@eval_app.command("open")
def eval_open(
    n: int = N_OPTION,
    seed: int = SEED_OPTION,
) -> None:
    mode = ModeConfig(seed=seed)
    initialize_runtime(
        cpu_threads=mode.cpu_threads,
        use_gpu=mode.use_gpu,
        gpu_id=mode.gpu_id,
        logger=logger,
    )
    logger.info("eval open start n=%s seed=%s", n, seed)
    config = default_config()
    report_path = run_open_eval(config=config, n=n, seed=seed)
    logger.info("eval open complete report=%s", report_path)
    console.print(f"Open eval report: {report_path}")


@eval_app.command("sealed")
def eval_sealed(
    suite: Path = SUITE_OPTION,
    n: int = N_OPTION,
    seed: int | None = SEALED_SEED_OPTION,
    reveal_seed: bool = REVEAL_SEED_OPTION,
) -> None:
    logger.info("eval sealed start n=%s seed=%s suite=%s", n, seed, suite)
    config = default_config()
    result = run_sealed_eval(
        config=config,
        suite_path=suite,
        n=n,
        seed=seed,
        reveal_seed=reveal_seed,
    )
    logger.info("eval sealed complete report=%s", result.report_path)
    console.print(f"Sealed eval report: {result.report_path}")
    console.print(f"Commitment: {result.commitment_hash}")
    if result.seed_hex is not None:
        console.print(f"Seed: {result.seed_hex}")


@skills_app.command("list")
def skills_list() -> None:
    initialize_runtime(logger=logger)
    logger.info("skills list start")
    config = default_config()
    registry = SkillRegistry.load(config.paths.skills_registry)
    if not registry.skills:
        console.print("No skills registered")
        return
    for skill in registry.skills:
        console.print(f"{skill.skill_id}: {skill.description}")


if __name__ == "__main__":
    app()
