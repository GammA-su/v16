#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
TARGET="$SCRIPT_DIR/tools/run_bvps_abs_only.sh"

if [ -x "$TARGET" ]; then
  exec "$TARGET" "$@"
fi

echo "missing $TARGET" >&2
exit 1
