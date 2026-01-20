#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 N" >&2
}

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

N="$1"
if ! [[ "$N" =~ ^[0-9]+$ ]]; then
  echo "N must be a positive integer" >&2
  exit 2
fi
if [ "$N" -le 0 ]; then
  echo "N must be greater than zero" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d runs ]; then
  echo "missing runs/ directory" >&2
  exit 1
fi

mapfile -t ucrs < <(uv run python tools/latest_ucrs.py --n "$N")

if [ "${#ucrs[@]}" -eq 0 ]; then
  echo "no runs/*/ucr.json files found" >&2
  exit 1
fi

for ucr in "${ucrs[@]}"; do
  name="$(basename "$(dirname "$ucr")")"
  uv run python ./tools/regress_add.py "$ucr" --name "$name"
done
