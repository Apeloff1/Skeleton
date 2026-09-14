import json

import pytest

from core.execution_receipts import ExecutionReceiptStore, ReceiptIntegrityError


def _write(store, operation_id="a" * 32, result=None):
    return store.write(
        operation_id=operation_id,
        capability_id="studio",
        action="project.create",
        executor="native.studio.project.create",
        executor_version=1,
        effect_class="state",
        replay_safe=True,
        input_artifact_manifest_id="f" * 32,
        result=result or {"project_id": "p1", "state": "created"},
    )


def test_receipt_round_trip_and_cas_result_round_trip(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    receipt = _write(store)
    assert store.read("a" * 32) == receipt
    assert store.list_recent(limit=1) == [receipt]
    assert store.load_result(receipt) == {"project_id": "p1", "state": "created"}
    assert receipt.result_artifact_id
    assert receipt.result_summary["state"] == "created"
    assert receipt.input_artifact_manifest_id == "f" * 32


def test_receipt_is_write_once_but_identical_result_is_idempotent(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    first = _write(store, "b" * 32, {"state": "created"})
    second = _write(store, "b" * 32, {"state": "created"})
    assert second == first

    with pytest.raises(ReceiptIntegrityError, match="write-once"):
        _write(store, "b" * 32, {"state": "mutated"})


def test_tampered_receipt_fails_closed(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    operation_id = "c" * 32
    _write(store, operation_id, {"session_id": "s1"})
    path = tmp_path / f"{operation_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["receipt"]["result_sha256"] = "0" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReceiptIntegrityError, match="checksum mismatch"):
        store.read(operation_id)


def test_tampered_result_chunk_fails_closed(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    receipt = _write(store, "d" * 32, {"state": "created", "blob": "x" * 100})
    manifest = store.results.load_manifest(receipt.result_artifact_id)
    chunk_path = store.results._chunk_path(manifest.chunks[0])
    chunk_path.write_bytes(b"tampered")
    with pytest.raises(ReceiptIntegrityError, match="integrity"):
        store.load_result(receipt)


def test_receipt_operation_id_must_be_hex(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    with pytest.raises(ValueError, match="hexadecimal"):
        store.read("../../escape")


def test_recent_limit_is_bounded(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    with pytest.raises(ValueError, match="between 0 and 500"):
        store.list_recent(limit=501)


def test_stats_include_result_cas(tmp_path):
    store = ExecutionReceiptStore(tmp_path)
    _write(store)
    stats = store.stats()
    assert stats["receipts"] == 1
    assert stats["results"]["manifests"] == 1
    assert stats["version"] == 2
