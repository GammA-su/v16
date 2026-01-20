from __future__ import annotations

from pathlib import Path

from eidolon_v16.cli_utils import sanitize_ansi_path


def test_sanitize_ansi_path_opens_file(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("ok")
    colored = f"\x1b[36m{target}\x1b[0m"
    sanitized = sanitize_ansi_path(f"  {colored}  ")
    assert Path(sanitized).read_text() == "ok"
