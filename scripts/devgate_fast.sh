#!/usr/bin/env bash
set -euo pipefail

echo "== ruff =="
uv run ruff check .

echo "== mypy =="
uv run mypy .

echo "== unit tests =="
uv run pytest -q

echo "== sealed smoke gate =="
./scripts/check_sealed_smoke.sh
