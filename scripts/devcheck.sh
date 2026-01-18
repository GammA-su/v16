#!/usr/bin/env bash
set -euo pipefail

export EIDOLON_RUNS_DIR="${EIDOLON_RUNS_DIR:-./runs}"

uv run ruff check .
uv run mypy .
uv run pytest -q

uv run python -m eidolon_v16.cli eval suite --suite discovery-suite.yaml
