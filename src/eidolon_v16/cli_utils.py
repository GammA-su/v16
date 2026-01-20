from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def sanitize_ansi_path(value: str) -> str:
    return _ANSI_RE.sub("", value).strip()
