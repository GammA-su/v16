#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUNS_DIR=""
cleanup_runs="0"
if [ -n "${EIDOLON_RUNS_DIR:-}" ]; then
  RUNS_DIR="$EIDOLON_RUNS_DIR"
elif [ "${EIDOLON_KEEP_RUNS:-0}" = "1" ]; then
  RUNS_DIR="$REPO_ROOT/runs"
else
  RUNS_DIR="$(mktemp -d)"
  cleanup_runs="1"
fi

mkdir -p "$RUNS_DIR"
export EIDOLON_RUNS_DIR="$RUNS_DIR"

if [ "$cleanup_runs" = "1" ]; then
  trap 'rm -rf "$RUNS_DIR"' EXIT
fi

LOG_DIR="$RUNS_DIR/gate_logs"
mkdir -p "$LOG_DIR"

GATE_TIMEOUT_S="${EIDOLON_GATE_TIMEOUT_S:-1200}"
GATE_MODE="default"
if [ "${EIDOLON_GATE_FULL:-0}" = "1" ]; then
  GATE_MODE="full"
elif [ "${EIDOLON_GATE_FAST:-0}" = "1" ]; then
  GATE_MODE="fast"
fi

SUITE_PATH="discovery-suite.yaml"
SUITE_DESC="suite=discovery-suite.yaml seeds=as-defined tasks=as-defined"

if [ "$GATE_MODE" != "full" ]; then
  SUITE_DIR="$RUNS_DIR/gate_suites"
  mkdir -p "$SUITE_DIR"
  SUITE_PATH="$SUITE_DIR/discovery-suite-$GATE_MODE.json"
  uv run python - "$GATE_MODE" "$SUITE_PATH" <<'PY'
import json
import sys
from pathlib import Path

from eidolon_v16.eval.suite import _load_suite_yaml

mode = sys.argv[1]
out_path = Path(sys.argv[2])
suite_path = Path("discovery-suite.yaml")

suite_spec = _load_suite_yaml(suite_path.read_bytes(), suite_path)

if mode == "fast":
    seeds = [suite_spec.seeds[0] if suite_spec.seeds else 0]
    wanted = {"arith_01", "list_01", "world_01", "bvps_abs_01"}
    tasks = [
        {"name": task.name, "path": str(task.path)}
        for task in suite_spec.tasks
        if task.name in wanted
    ]
    suite_name = "discovery-suite-fast"
elif mode == "default":
    seeds = suite_spec.seeds[:2] if suite_spec.seeds else [0]
    tasks = [{"name": task.name, "path": str(task.path)} for task in suite_spec.tasks]
    suite_name = "discovery-suite-default"
else:
    raise SystemExit(f"unsupported gate mode: {mode}")

payload = {"suite_name": suite_name, "tasks": tasks, "seeds": seeds}
out_path.write_text(json.dumps(payload, indent=2))
PY
  if [ "$GATE_MODE" = "fast" ]; then
    SUITE_DESC="suite=$SUITE_PATH seeds=1 tasks=arith_01,list_01,world_01,bvps_abs_01"
  else
    SUITE_DESC="suite=$SUITE_PATH seeds=2 tasks=all"
  fi
fi

parse_suite_report() {
  local log_file="$1"
  local line
  line="$(rg -o '^Suite report: .*' "$log_file" 2>/dev/null || true)"
  line="$(printf '%s\n' "$line" | tail -n 1)"
  if [ -z "$line" ]; then
    echo "could not parse suite report from $log_file" >&2
    return 1
  fi
  printf '%s\n' "${line#Suite report: }"
}

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

echo "== gate mode =="
echo "mode: $GATE_MODE"
echo "suite: $SUITE_DESC"
echo "suite timeout: ${GATE_TIMEOUT_S}s"

echo "== pytest =="
uv run pytest -q

echo "== discovery suite (default) =="
suite_default_log="$LOG_DIR/suite_default.log"
timeout "${GATE_TIMEOUT_S}s" \
  uv run python -m eidolon_v16.cli eval suite --suite "$SUITE_PATH" | tee "$suite_default_log" >/dev/null
suite_default_report="$(parse_suite_report "$suite_default_log")"

echo "== discovery suite (manifest batch) =="
suite_batch_log="$LOG_DIR/suite_batch.log"
EIDOLON_MANIFEST_BATCH=1 \
  timeout "${GATE_TIMEOUT_S}s" \
  uv run python -m eidolon_v16.cli eval suite --suite "$SUITE_PATH" | tee "$suite_batch_log" >/dev/null
suite_batch_report="$(parse_suite_report "$suite_batch_log")"

smoke_suite="baselines/sealed-smoke.baseline.json"
smoke_base="baselines/sealed-smoke.commitment.txt"

if [ ! -f "$smoke_base" ]; then
  echo "missing $smoke_base (create it from a known-good run)" >&2
  exit 2
fi

echo "== sealed smoke (default) =="
smoke_default_log="$LOG_DIR/sealed_smoke_default.log"
uv run python -m eidolon_v16.cli eval sealed --suite "$smoke_suite" --n 10 --seed 0 \
  | tee "$smoke_default_log" >/dev/null
smoke_default_commit="$(parse_commitment "$smoke_default_log")"
smoke_baseline="$(tr -d '\r\n' < "$smoke_base")"

if [ "$smoke_default_commit" != "$smoke_baseline" ]; then
  echo "sealed smoke commitment changed (default)" >&2
  echo "baseline: $smoke_baseline" >&2
  echo "current : $smoke_default_commit" >&2
  exit 1
fi

echo "== sealed smoke (manifest batch) =="
smoke_batch_log="$LOG_DIR/sealed_smoke_batch.log"
EIDOLON_MANIFEST_BATCH=1 \
  uv run python -m eidolon_v16.cli eval sealed --suite "$smoke_suite" --n 10 --seed 0 \
  | tee "$smoke_batch_log" >/dev/null
smoke_batch_commit="$(parse_commitment "$smoke_batch_log")"

if [ "$smoke_batch_commit" != "$smoke_baseline" ]; then
  echo "sealed smoke commitment changed (batch)" >&2
  echo "baseline: $smoke_baseline" >&2
  echo "current : $smoke_batch_commit" >&2
  exit 1
fi

if [ "$smoke_default_commit" != "$smoke_batch_commit" ]; then
  echo "sealed smoke commitment batch invariance failed" >&2
  echo "default: $smoke_default_commit" >&2
  echo "batch  : $smoke_batch_commit" >&2
  exit 1
fi

skills_suite="baselines/sealed-smoke-skills.baseline.json"
skills_base="baselines/sealed-smoke-skills.commitment.txt"
skills_status="skipped"
skills_default_commit=""
skills_batch_commit=""
skills_invariance="n/a"

if [ -f "$skills_base" ]; then
  if [ ! -f "$skills_suite" ]; then
    echo "missing $skills_suite (expected alongside $skills_base)" >&2
    exit 2
  fi
  echo "== sealed smoke skills (default) =="
  skills_default_log="$LOG_DIR/sealed_smoke_skills_default.log"
  EIDOLON_AUTO_SKILLS=1 \
    uv run python -m eidolon_v16.cli eval sealed --suite "$skills_suite" --n 10 --seed 0 \
    | tee "$skills_default_log" >/dev/null
  skills_default_commit="$(parse_commitment "$skills_default_log")"
  skills_baseline="$(tr -d '\r\n' < "$skills_base")"

  if [ "$skills_default_commit" != "$skills_baseline" ]; then
    echo "sealed smoke skills commitment changed (default)" >&2
    echo "baseline: $skills_baseline" >&2
    echo "current : $skills_default_commit" >&2
    exit 1
  fi

  echo "== sealed smoke skills (manifest batch) =="
  skills_batch_log="$LOG_DIR/sealed_smoke_skills_batch.log"
  EIDOLON_AUTO_SKILLS=1 EIDOLON_MANIFEST_BATCH=1 \
    uv run python -m eidolon_v16.cli eval sealed --suite "$skills_suite" --n 10 --seed 0 \
    | tee "$skills_batch_log" >/dev/null
  skills_batch_commit="$(parse_commitment "$skills_batch_log")"

  if [ "$skills_batch_commit" != "$skills_baseline" ]; then
    echo "sealed smoke skills commitment changed (batch)" >&2
    echo "baseline: $skills_baseline" >&2
    echo "current : $skills_batch_commit" >&2
    exit 1
  fi

  if [ "$skills_default_commit" != "$skills_batch_commit" ]; then
    echo "sealed smoke skills commitment batch invariance failed" >&2
    echo "default: $skills_default_commit" >&2
    echo "batch  : $skills_batch_commit" >&2
    exit 1
  fi

  skills_status="checked"
  skills_invariance="ok"
fi

echo "PASS gate"
echo "pytest: ok"
echo "suite reports: $suite_default_report | $suite_batch_report"
echo "sealed-smoke commitments: default=$smoke_default_commit batch=$smoke_batch_commit baseline=$smoke_baseline"
echo "sealed-smoke batch invariance: ok"
if [ "$skills_status" = "checked" ]; then
  echo "sealed-smoke-skills commitments: default=$skills_default_commit batch=$skills_batch_commit baseline=$skills_baseline"
  echo "sealed-smoke-skills batch invariance: $skills_invariance"
else
  echo "sealed-smoke-skills baseline: skipped (missing $skills_base)"
fi
