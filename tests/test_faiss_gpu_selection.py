from __future__ import annotations

import logging

import pytest

from eidolon_v16 import runtime


class DummyFaiss:
    @staticmethod
    def get_num_gpus() -> int:
        return 1


def test_init_faiss_gpu_invalid_id_disables(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setattr(runtime, "_faiss_gpu_checked", False)
    monkeypatch.setattr(runtime, "_faiss_gpu_ready", False)
    monkeypatch.setattr(runtime, "_load_faiss", lambda: DummyFaiss())

    caplog.set_level(logging.WARNING)
    logger = logging.getLogger("eidolon_v16.runtime.test")
    ok = runtime.init_faiss_gpu(1, logger)

    assert ok is False
    messages = [record.getMessage() for record in caplog.records]
    assert any("requested gpu_id=1" in msg and "available=1" in msg for msg in messages)
