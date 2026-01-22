#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
perf_runs_root="${EIDOLON_RUNS_DIR:-$REPO_ROOT/runs}"
perf_root="$perf_runs_root/perf/$timestamp"
default_dir="$perf_root/default"
batch_dir="$perf_root/batch"

mkdir -p "$default_dir" "$batch_dir"

suite_path="discovery-suite.yaml"

git_sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
git_dirty="false"
if git status --porcelain >/dev/null 2>&1; then
  if [ -n "$(git status --porcelain)" ]; then
    git_dirty="true"
  fi
fi
if [ "$git_dirty" = "true" ] && [ "${ALLOW_DIRTY:-0}" != "1" ]; then
  echo "working tree is dirty; set ALLOW_DIRTY=1 to proceed" >&2
  exit 1
fi

hostname_value="$(hostname 2>/dev/null || echo unknown)"
gpu_name="unknown"
if command -v nvidia-smi >/dev/null 2>&1; then
  gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [ -z "$gpu_name" ]; then
    gpu_name="unknown"
  fi
fi

cpu_model="unknown"
if [ -r /proc/cpuinfo ]; then
  cpu_model="$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo | sed 's/^[[:space:]]*//')"
  if [ -z "$cpu_model" ]; then
    cpu_model="unknown"
  fi
fi

if [ -z "${EIDOLON_MANIFEST_BATCH+x}" ]; then
  export EIDOLON_MANIFEST_BATCH=1
fi
if [ "${EIDOLON_BVPS_PERSIST_CACHE:-0}" = "1" ] && [ -z "${EIDOLON_BVPS_CACHE_SKIP_MODEL+x}" ]; then
  export EIDOLON_BVPS_CACHE_SKIP_MODEL=1
fi

echo "== perf snapshot =="
echo "timestamp: $timestamp"
echo "suite: $suite_path"
echo "out: $perf_root"
echo "default out: $default_dir"
echo "batch out: $batch_dir"
echo "EIDOLON_MANIFEST_BATCH: ${EIDOLON_MANIFEST_BATCH:-<unset>}"
echo "EIDOLON_BVPS_PERSIST_CACHE: ${EIDOLON_BVPS_PERSIST_CACHE:-0}"
echo "EIDOLON_BVPS_CACHE_SKIP_MODEL: ${EIDOLON_BVPS_CACHE_SKIP_MODEL:-<unset>}"
echo "EIDOLON_BVPS_PERSIST_PRELOAD: ${EIDOLON_BVPS_PERSIST_PRELOAD:-0}"
echo "git_sha: $git_sha"
echo "git_dirty: $git_dirty"
echo "hostname: $hostname_value"
echo "gpu_name: $gpu_name"
echo "cpu_model: $cpu_model"

default_cmd="uv run python -m eidolon_v16.cli eval suite --suite $suite_path --out-dir $default_dir"
batch_cmd="EIDOLON_MANIFEST_BATCH=1 uv run python -m eidolon_v16.cli eval suite --suite $suite_path --out-dir $batch_dir"
echo "default cmd: $default_cmd"
echo "batch cmd: $batch_cmd"

if [ "${EIDOLON_BVPS_PERSIST_CACHE:-0}" = "1" ]; then
  prewarm_suite="$perf_root/bvps-prewarm.yaml"
  prewarm_out="$perf_root/prewarm"
  cat >"$prewarm_suite" <<'EOF'
suite_name: bvps-prewarm
seeds: [0]
tasks:
  - bvps_abs_01
  - bvps_even_01
  - bvps_max_01
EOF
  prewarm_cmd="EIDOLON_BVPS_PERSIST_CACHE=1 uv run python -m eidolon_v16.cli eval suite --suite $prewarm_suite --out-dir $prewarm_out"
  echo "prewarm cmd: $prewarm_cmd"
  EIDOLON_BVPS_PERSIST_CACHE=1 \
    uv run python -m eidolon_v16.cli eval suite --suite "$prewarm_suite" --out-dir "$prewarm_out" >/dev/null
fi

uv run python -m eidolon_v16.cli eval suite --suite "$suite_path" --out-dir "$default_dir"
EIDOLON_MANIFEST_BATCH=1 \
  uv run python -m eidolon_v16.cli eval suite --suite "$suite_path" --out-dir "$batch_dir"

default_report="$default_dir/report.json"
batch_report="$batch_dir/report.json"

echo "== suite report summary (default) =="
uv run python scripts/suite_report_summary.py "$default_report" | tee "$default_dir/summary.txt"

echo "== suite report worst (default) =="
uv run python scripts/suite_report_worst.py "$default_report" | tee "$default_dir/worst.txt"

echo "== suite report summary (batch) =="
uv run python scripts/suite_report_summary.py "$batch_report" | tee "$batch_dir/summary.txt"

echo "== suite report worst (batch) =="
uv run python scripts/suite_report_worst.py "$batch_report" | tee "$batch_dir/worst.txt"

history_path="$perf_runs_root/perf_history.jsonl"
mkdir -p "$(dirname "$history_path")"

python - "$timestamp" "$default_report" "$batch_report" "$history_path" \
  "$git_sha" "$git_dirty" "$hostname_value" "$gpu_name" "$cpu_model" <<'PY'
import json
import sys
from pathlib import Path

timestamp = sys.argv[1]
default_report = Path(sys.argv[2])
batch_report = Path(sys.argv[3])
history_path = Path(sys.argv[4])
git_sha = sys.argv[5]
git_dirty = sys.argv[6]
hostname_value = sys.argv[7]
gpu_name = sys.argv[8]
cpu_model = sys.argv[9]

def load_metrics(path: Path) -> dict:
    data = json.loads(path.read_text())
    metrics = data.get("metrics") if isinstance(data, dict) else None
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "total_ms_mean": metrics.get("total_ms_mean", 0),
        "total_ms_p95": metrics.get("total_ms_p95", 0),
        "total_ms_p99": metrics.get("total_ms_p99", 0),
        "total_ms_sum": metrics.get("total_ms_sum", 0),
        "lane_ms_sum": metrics.get("lane_ms_sum", {}),
        "overhead_ms_p95": metrics.get("overhead_ms_p95", 0),
        "overhead_residual_ms_p95": metrics.get("overhead_residual_ms_p95", 0),
        "verify_phase_ms_p99": metrics.get("verify_phase_ms_p99", 0),
        "verify_artifact_ms_mean": metrics.get("verify_artifact_ms_mean", 0),
        "verify_artifact_ms_p95": metrics.get("verify_artifact_ms_p95", 0),
        "verify_admission_ms_mean": metrics.get("verify_admission_ms_mean", 0),
        "verify_admission_ms_p95": metrics.get("verify_admission_ms_p95", 0),
    }

record = {
    "timestamp": timestamp,
    "suite": "discovery-suite.yaml",
    "default_report": str(default_report),
    "batch_report": str(batch_report),
    "git_sha": git_sha,
    "git_dirty": git_dirty == "true",
    "hostname": hostname_value,
    "gpu_name": gpu_name,
    "cpu_model": cpu_model,
    "default_metrics": load_metrics(default_report),
    "batch_metrics": load_metrics(batch_report),
}

history_path.write_text(
    history_path.read_text() + json.dumps(record, separators=(",", ":")) + "\n"
    if history_path.exists()
    else json.dumps(record, separators=(",", ":")) + "\n"
)
print(f"appended {history_path}")
PY
