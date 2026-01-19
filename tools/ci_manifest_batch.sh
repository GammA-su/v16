#!/usr/bin/env bash
set -euo pipefail

EXPECTED="298175f282bd70aa8baf09347af0b147493fe14e8e20610000f1648338b282b2"
LOG="${LOG:-/tmp/eidolon_manifest_batch_ci.log}"

EIDOLON_RUNS_DIR="${EIDOLON_RUNS_DIR:-./runs}" uv run python -m eidolon_v16.cli eval suite \
  --suite discovery-suite.yaml >/dev/null

EIDOLON_RUNS_DIR="${EIDOLON_RUNS_DIR:-./runs}" EIDOLON_MANIFEST_BATCH=1 \
  uv run python -m eidolon_v16.cli eval suite --suite discovery-suite.yaml >/dev/null

EIDOLON_RUNS_DIR="${EIDOLON_RUNS_DIR:-./runs}" uv run python -m eidolon_v16.cli eval sealed \
  --suite baselines/sealed-smoke.baseline.json --n 10 --seed 0 | tee "$LOG" >/dev/null

NEW="$(rg -o 'commitment=[0-9a-f]{64}' "$LOG" | tail -n 1 | cut -d= -f2 || true)"
if [ -z "${NEW}" ]; then
  NEW="$(awk '
    $0 ~ /^Commitment:/ {want=1; next}
    want && $0 ~ /^[0-9a-f]{64}$/ {print; exit 0}
  ' "$LOG" || true)"
fi

if [ -z "${NEW}" ]; then
  echo "could not parse commitment from $LOG" >&2
  exit 3
fi

echo "expected: $EXPECTED"
echo "current : $NEW"

[ "$NEW" = "$EXPECTED" ] || { echo "sealed smoke commitment changed" >&2; exit 1; }
