#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q
EIDOLON_RUNS_DIR=./runs uv run python -m eidolon_v16.cli eval suite --suite discovery-suite.yaml >/dev/null

# if you have a sealed smoke suite:
if [ -f baselines/sealed_smoke.yaml ] || [ -f baselines/sealed_smoke.json ] || [ -f baselines/sealed_smoke.txt ]; then
  SUITE="$(ls -1 baselines/sealed_smoke.* | head -n 1)"
  EIDOLON_RUNS_DIR=./runs uv run python -m eidolon_v16.cli eval sealed --suite "$SUITE" --n 25 --seed 0 >/dev/null
fi

echo "devgate OK"
