from eidolon_v16.ucr.models import TaskInput


def test_task_kind_infers_arith_prefix() -> None:
    payload = {"task": "ARITH: 1 + 1"}
    task_input = TaskInput.from_raw(payload)
    assert task_input.normalized["kind"] == "arith"


def test_task_kind_infers_bvps_prefix() -> None:
    payload = {"task": "BVPS: dummy"}
    task_input = TaskInput.from_raw(payload)
    assert task_input.normalized["kind"] == "bvps"
