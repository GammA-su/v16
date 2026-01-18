#!/usr/bin/env bash
set -euo pipefail

export EIDOLON_RUNS_DIR="${EIDOLON_RUNS_DIR:-./runs}"

echo "[1/2] open suite..."
uv run python -m eidolon_v16.cli eval suite --suite-file discovery-suite.yaml

latest="$(find runs/suites -type f -name report.json -print0 | xargs -0 ls -t | head -n 1)"
uv run python scripts/suite_report_summary.py "$latest"

echo "[2/2] sealed eval (small n)..."
uv run python -m eidolon_v16.cli eval sealed --suite-file discovery-suite.yaml --n 25 --seed 0

echo "OK"
