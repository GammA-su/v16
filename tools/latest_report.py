from __future__ import annotations

from pathlib import Path


def main() -> int:
    base = Path("runs") / "suites"
    if not base.exists():
        return 1
    candidates = list(base.glob("*/report.json"))
    if not candidates:
        return 1
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    print(latest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
