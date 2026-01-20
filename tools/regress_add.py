from __future__ import annotations

import argparse
import json
from pathlib import Path

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.ucr.canonical import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a regression vault entry from a run UCR.",
    )
    parser.add_argument("ucr_path", type=Path)
    parser.add_argument("--name", help="Output name (defaults to run directory name).")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tests/regress"),
        help="Output directory for regression fixtures.",
    )
    parser.add_argument(
        "--artifact-store",
        type=Path,
        default=Path("artifact_store"),
        help="Artifact store root containing solution payloads.",
    )
    args = parser.parse_args()

    ucr_payload = json.loads(args.ucr_path.read_text())
    solution_refs = ucr_payload.get("solution_artifacts", [])
    if not solution_refs:
        raise SystemExit("UCR missing solution_artifacts")
    solution_hash = str(solution_refs[0].get("hash", ""))
    if not solution_hash:
        raise SystemExit("UCR missing solution_artifacts hash")

    store = ArtifactStore(args.artifact_store)
    try:
        solution_payload = store.read_json_by_hash(solution_hash)
    except FileNotFoundError:
        run_artifacts = args.ucr_path.parent / "artifacts"
        fallback = run_artifacts / f"solution-{solution_hash}.json"
        if not fallback.exists():
            raise
        solution_payload = json.loads(fallback.read_text())

    record = {
        "ucr": ucr_payload,
        "solution_artifact": {
            "hash": solution_hash,
            "payload": solution_payload,
        },
    }

    name = args.name or args.ucr_path.parent.name or args.ucr_path.stem
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{name}.json"
    out_path.write_bytes(canonical_json_bytes(record))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
