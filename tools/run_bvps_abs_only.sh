#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

suite_path="/tmp/bvps_abs_only.yaml"
cat >"$suite_path" <<'EOF'
suite_name: bvps-abs-only
seeds: [0,1,2,3]
tasks:
  - bvps_abs_01
EOF

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="runs/suites/${timestamp}-bvps-abs-only"

EIDOLON_RUNS_DIR=./runs EIDOLON_MANIFEST_BATCH=1 \
  uv run python -m eidolon_v16.cli eval suite --suite "$suite_path" --out-dir "$out_dir"

echo "out_dir=$out_dir"

uv run python scripts/suite_report_summary.py "$out_dir/report.json"
uv run python scripts/suite_report_worst.py "$out_dir/report.json" --top 10
