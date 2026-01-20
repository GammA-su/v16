#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--yes]" >&2
}

accept="0"
if [ "${1:-}" = "--yes" ]; then
  accept="1"
  shift
fi

if [ "$#" -ne 0 ]; then
  usage
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

N=10
SEED=0

smoke_suite="baselines/sealed-smoke.baseline.json"
smoke_base="baselines/sealed-smoke.commitment.txt"
skills_suite="baselines/sealed-smoke-skills.baseline.json"
skills_base="baselines/sealed-smoke-skills.commitment.txt"

if [ ! -f "$smoke_suite" ]; then
  echo "missing $smoke_suite" >&2
  exit 2
fi
if [ ! -f "$skills_suite" ]; then
  echo "missing $skills_suite" >&2
  exit 2
fi

parse_commitment() {
  local log_file="$1"
  local line
  line="$(rg -o 'Commitment: [0-9a-f]{64}' "$log_file" 2>/dev/null || true)"
  line="$(printf '%s\n' "$line" | tail -n 1)"
  if [ -n "$line" ]; then
    printf '%s\n' "${line#Commitment: }"
    return 0
  fi
  line="$(rg -o 'commitment=[0-9a-f]{64}' "$log_file" 2>/dev/null || true)"
  line="$(printf '%s\n' "$line" | tail -n 1)"
  if [ -n "$line" ]; then
    printf '%s\n' "${line#commitment=}"
    return 0
  fi
  line="$(awk '/^Commitment:/{value=$2} END{print value}' "$log_file")"
  if [ -n "$line" ]; then
    printf '%s\n' "$line"
    return 0
  fi
  echo "could not parse commitment from $log_file" >&2
  return 1
}

run_sealed() {
  local suite="$1"
  local auto_skills="$2"
  local manifest_batch="$3"
  local runs_dir=""
  local cleanup="0"

  if [ -n "${EIDOLON_RUNS_DIR:-}" ]; then
    runs_dir="$EIDOLON_RUNS_DIR"
  elif [ "${EIDOLON_KEEP_RUNS:-0}" = "1" ]; then
    runs_dir="$REPO_ROOT/runs"
  else
    runs_dir="$(mktemp -d)"
    cleanup="1"
  fi

  mkdir -p "$runs_dir"

  local log_file
  log_file="$(mktemp)"

  if [ "$auto_skills" = "1" ]; then
    if [ "$manifest_batch" = "1" ]; then
      EIDOLON_RUNS_DIR="$runs_dir" EIDOLON_AUTO_SKILLS=1 EIDOLON_MANIFEST_BATCH=1 \
        uv run python -m eidolon_v16.cli eval sealed --suite "$suite" --n "$N" --seed "$SEED" \
        | tee "$log_file" >/dev/null
    else
      EIDOLON_RUNS_DIR="$runs_dir" EIDOLON_AUTO_SKILLS=1 \
        uv run python -m eidolon_v16.cli eval sealed --suite "$suite" --n "$N" --seed "$SEED" \
        | tee "$log_file" >/dev/null
    fi
  else
    if [ "$manifest_batch" = "1" ]; then
      EIDOLON_RUNS_DIR="$runs_dir" EIDOLON_MANIFEST_BATCH=1 \
        uv run python -m eidolon_v16.cli eval sealed --suite "$suite" --n "$N" --seed "$SEED" \
        | tee "$log_file" >/dev/null
    else
      EIDOLON_RUNS_DIR="$runs_dir" \
        uv run python -m eidolon_v16.cli eval sealed --suite "$suite" --n "$N" --seed "$SEED" \
        | tee "$log_file" >/dev/null
    fi
  fi

  local commit
  commit="$(parse_commitment "$log_file")"
  rm -f "$log_file"

  if [ "$cleanup" = "1" ]; then
    rm -rf "$runs_dir"
  fi

  printf '%s\n' "$commit"
}

smoke_default_commit="$(run_sealed "$smoke_suite" "0" "0")"
smoke_batch_commit="$(run_sealed "$smoke_suite" "0" "1")"

if [ "$smoke_default_commit" != "$smoke_batch_commit" ]; then
  echo "sealed-smoke commitment batch invariance failed" >&2
  echo "default: $smoke_default_commit" >&2
  echo "batch  : $smoke_batch_commit" >&2
  exit 1
fi

skills_default_commit="$(run_sealed "$skills_suite" "1" "0")"
skills_batch_commit="$(run_sealed "$skills_suite" "1" "1")"

if [ "$skills_default_commit" != "$skills_batch_commit" ]; then
  echo "sealed-smoke-skills commitment batch invariance failed" >&2
  echo "default: $skills_default_commit" >&2
  echo "batch  : $skills_batch_commit" >&2
  exit 1
fi

smoke_old="$(tr -d '\r\n' < "$smoke_base" 2>/dev/null || true)"
skills_old="$(tr -d '\r\n' < "$skills_base" 2>/dev/null || true)"

echo "sealed-smoke: old=${smoke_old:-<missing>} new=$smoke_default_commit"
echo "sealed-smoke-skills: old=${skills_old:-<missing>} new=$skills_default_commit"

if [ "$accept" != "1" ]; then
  echo "re-run with --yes to write baselines" >&2
  exit 1
fi

printf '%s\n' "$smoke_default_commit" > "$smoke_base"
printf '%s\n' "$skills_default_commit" > "$skills_base"

echo "baselines updated"
