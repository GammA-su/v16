from __future__ import annotations

from pathlib import Path

import pytest

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.bvps import cache as bvps_cache


def test_bvps_cache_touch_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ArtifactStore(tmp_path / "artifact_store")
    bvps_cache._TOUCHED_PERSIST_DIRS.clear()

    calls = {"count": 0}
    original = store.load_manifest

    def wrapped() -> object:
        calls["count"] += 1
        return original()

    monkeypatch.setattr(store, "load_manifest", wrapped)

    assert bvps_cache.touch_persist_once(store) is True
    assert bvps_cache.touch_persist_once(store) is False
    assert calls["count"] == 1
