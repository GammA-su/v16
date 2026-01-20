from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="List newest run UCRs.")
    parser.add_argument("--n", type=int, default=1)
    args = parser.parse_args()
    if args.n <= 0:
        return 2
    base = Path("runs")
    if not base.exists():
        return 1
    candidates = list(base.glob("*/ucr.json"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates[: args.n]:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
