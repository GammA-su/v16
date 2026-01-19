#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q
./tools/ci_manifest_batch.sh

echo "devgate OK"
