import json

import pytest

from core.execution_receipts import ExecutionReceiptStore, ReceiptIntegrityError


def test_receipt_round_trip_and_recent_listing(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    receipt = store.write(
        operation_id="a" * 32,
        capability_id="studio",
        action="project.create",
        executor="native.studio.project.create",
        result={"project_id": "p1", "state": "created"},
    )
    assert store.read("a" * 32) == receipt
    assert store.list_recent(limit=1) == [receipt]


def test_receipt_is_write_once_but_identical_write_is_idempotent(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    kwargs = dict(
        operation_id="b" * 32,
        capability_id="studio",
        action="project.create",
        executor="native.studio.project.create",
        result={"state": "created"},
    )
    first = store.write(**kwargs)
    second = store.write(**kwargs)
    assert second == first

    with pytest.raises(ReceiptIntegrityError, match="write-once"):
        store.write(**{**kwargs, "result": {"state": "mutated"}})


def test_tampered_receipt_fails_closed(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    operation_id = "c" * 32
    store.write(
        operation_id=operation_id,
        capability_id="playables",
        action="playable.launch",
        executor="native.playables.playable.launch",
        result={"session_id": "s1"},
    )
    path = tmp_path / f"{operation_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["receipt"]["result"]["session_id"] = "evil"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ReceiptIntegrityError, match="checksum mismatch"):
        store.read(operation_id)


def test_receipt_operation_id_must_be_hex(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    with pytest.raises(ValueError, match="hexadecimal"):
        store.read("../../escape")


def test_recent_limit_is_bounded(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    with pytest.raises(ValueError, match="between 0 and 500"):
        store.list_recent(limit=501)
