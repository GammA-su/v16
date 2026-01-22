# EIDOLON v16

Deterministic, replayable "verified discovery machine" MVP. Every episode emits a UCR + witness packet with artifacts and verification lane verdicts. This repo is uv-first and Python 3.10 only to support faiss-gpu and numpy<2.

## Quickstart (bootstrap commands)

```bash
uv init --name eidolon_v16 --package
uv add pydantic rich typer
uv add numpy<2 faiss-gpu
uv add --dev pytest ruff mypy
```

## Run a demo episode

```bash
uv run eidolon episode run --task-file examples/tasks/arith_01.json
uv run eidolon episode replay --ucr runs/<episode_id>/ucr.json
uv run eidolon ledger verify
uv run python -c "from pathlib import Path; from eidolon_v16.ledger.chain import verify_chain; print(verify_chain(Path('ledger.chain.jsonl')))"
```

## Kernel adapter (stub vs http)

By default the stub kernel is used. To switch to an HTTP-backed kernel:

```bash
export EIDOLON_KERNEL=http
export EIDOLON_KERNEL_URL=http://localhost:8000
uv run eidolon episode run --task-file examples/tasks/arith_01.json
```

Expected endpoints:

- `POST /propose_interpretations` with JSON `{seed, task}` -> `{interpretations: [...]}`.
- `POST /propose_solution` with JSON `{seed, task, interpretation}` -> `{solution_kind, output, program?, trace?}`.
- `POST /critique` with JSON `{seed, task, solution}` -> `{critique}`.

Each call is logged as a `kernel_call` artifact with request/response hashes.

## Llama.cpp kernel

```bash
export EIDOLON_KERNEL=llamacpp
export EIDOLON_GGUF=/path/to/model.gguf
uv run eidolon episode run --task-file examples/tasks/arith_01.json
```

## Open eval (MVP)

```bash
uv run eidolon eval open --n 10 --seed 0
```

## Sealed eval (suite-driven)

```bash
uv run eidolon eval sealed --suite examples/suites/basic.yaml --n 10
```

## Skills registry

```bash
uv run eidolon skills list
```

## Tests + lint

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy src
```

## Server workflow

First-time setup:

```bash
uv sync
```

Daily loop:

```bash
bash scripts/gate.sh
```

When you intentionally accept new sealed behavior:

```bash
bash tools/bump_sealed_baselines.sh --yes
bash scripts/gate.sh
```

## Regression vault

Add the latest N UCRs to the vault:

```bash
uv run python tools/latest_ucrs.py --n 5
bash tools/regress_add_latest.sh 5
```

Verify vault fixtures:

```bash
uv run pytest -q tests/test_regress_vault.py
```

## Perf triage: BVPS abs-only

```bash
bash ./run_bvps_abs_only.sh
```

Expected result once BVPS cache is working: 1 slow run followed by 3 cache-hit fast runs.

Latest suite report helpers:

```bash
uv run python tools/latest_report.py
uv run python scripts/suite_report_summary.py "$(uv run python tools/latest_report.py)"
uv run python scripts/suite_report_worst.py "$(uv run python tools/latest_report.py)" --top 5
```

## Notes

- All important outputs are stored in the content-addressed `artifact_store/` and listed in `artifact_store/manifest.json`.
- UCRs and witness packets are also copied into `runs/<episode_id>/` for convenience, along with `runs/<episode_id>/artifacts/`.
- Determinism is enforced via canonical JSON, explicit seeds, and content hashes.
- Runtime initialization sets CPU threads to 16 by default and logs FAISS GPU availability for GPU id 0.
- Override run output location with `EIDOLON_RUNS_DIR` and ledger chain path with `EIDOLON_LEDGER_CHAIN`.

## Performance flags

- `EIDOLON_MANIFEST_BATCH=1` batches artifact manifest writes per episode to reduce verify overhead. Default off keeps current behavior; commitments are unchanged when off. Sealed smoke was verified unchanged when on.
