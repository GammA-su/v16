#!/usr/bin/env bash
set -euo pipefail

SUITE="${1:-baselines/sealed-smoke.baseline.json}"
BASE="baselines/sealed-smoke.commitment.txt"
N="${N:-10}"
SEED="${SEED:-0}"
LOG="${LOG:-/tmp/eidolon_sealed_smoke.log}"

if [ ! -f "$BASE" ]; then
  echo "missing $BASE (create it from a known-good run)" >&2
  exit 2
fi

EIDOLON_RUNS_DIR="${EIDOLON_RUNS_DIR:-./runs}" uv run python -m eidolon_v16.cli eval sealed \
  --suite "$SUITE" --n "$N" --seed "$SEED" | tee "$LOG" >/dev/null

# Prefer commitment=... from INFO line
NEW="$(rg -o 'commitment=[0-9a-f]{64}' "$LOG" | tail -n 1 | cut -d= -f2 || true)"

# Fallback: next non-empty line after "Commitment:"
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

OLD="$(tr -d '\r\n' < "$BASE")"

echo "baseline: $OLD"
echo "current : $NEW"

[ "$NEW" = "$OLD" ] || { echo "sealed smoke commitment changed" >&2; exit 1; }
