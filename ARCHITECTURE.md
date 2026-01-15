# Architecture Notes

## Data flow

1. Task input is normalized into a UCR-compatible `TaskInput`.
2. The kernel proposes interpretations and a solution candidate.
3. The orchestrator stores artifacts (solution, lane evidence, capsule, witness).
4. Verification lanes run (recompute, translation, consequence, anchors).
5. A decision is made and a witness packet is produced.
6. The UCR is serialized with canonical JSON and stored as an artifact.
7. A ledger event is appended to the SQLite hash-chain.

## Invariants

- Canonical JSON + SHA-256 for all content-addressed artifacts.
- Deterministic seeds for kernel, BVPS, and consequence checks.
- Fail-closed verification: a required lane must PASS to answer.
- UCR hash is computed with its own hash field blanked.
- Manifest root hash excludes the UCR artifact to avoid cycles.

## Modules

- `ucr/`: schemas, canonicalization, hashing.
- `artifacts/`: content-addressed store + manifest.
- `ledger/`: append-only SQLite hash-chain.
- `orchestrator/`: episode controller, budgets, decisions.
- `kernel/`: stub kernel interface and deterministic implementation.
- `bvps/`: typed DSL, interpreter, bounded CEGIS skeleton.
- `verify/`: lanes (recompute, translation, consequence, anchors).
- `worldlab/`: deterministic gridworld and rollout runner.
- `eval/`: open evaluation harness and canary checks.
- `skills/`: registry and admission gate skeleton.
- `language/`: patch format, scope, conservativity metadata.
- `capsules/`: repro bundles and regression runner.
- `ui/`: minimal Rich rendering helpers.
- `runtime.py`: logging, CPU thread defaults, and FAISS GPU initialization.
