from datetime import datetime, timezone
import pytest

from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.serialization import SerializationError, dumps, loads_object, receipt_from_dict


def receipt(**changes):
    now = datetime.now(timezone.utc).isoformat()
    values = dict(
        command="python",
        correlation_id="corr",
        fingerprint="f" * 64,
        started_at=now,
        finished_at=now,
        duration_ms=1.25,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=3,
        stderr_bytes=0,
        attempt=1,
    )
    values.update(changes)
    return ExecutionReceipt(**values)


def test_receipt_validates_nonnegative_metrics():
    with pytest.raises(ValueError):
        receipt(duration_ms=-1)
    with pytest.raises(ValueError):
        receipt(stdout_bytes=-1)
    with pytest.raises(ValueError):
        receipt(attempt=0)


def test_receipt_to_dict_contains_safe_metadata():
    item = receipt(metadata={"post_hook_failures": ["ValueError"]})
    payload = item.to_dict()
    assert payload["command"] == "python"
    assert payload["metadata"]["post_hook_failures"] == ["ValueError"]


def test_receipt_chain_hashes_and_verifies():
    chain = ReceiptChain()
    first = chain.append(receipt())
    second = chain.append(receipt(correlation_id="other"))
    assert first.previous_hash == chain.GENESIS
    assert second.previous_hash == first.receipt_hash
    assert chain.verify()
    assert chain.root_hash() == second.receipt_hash


def test_receipt_chain_capacity_is_bounded():
    chain = ReceiptChain(max_receipts=1)
    chain.append(receipt())
    with pytest.raises(RuntimeError):
        chain.append(receipt())


def test_receipt_now_failure_is_safe_default():
    item = ExecutionReceipt.now_failure(command="python", correlation_id="c", fingerprint="x")
    assert not item.ok
    assert item.stdout_bytes == 0
    assert item.stderr_bytes == 0


def test_serialization_handles_receipts_and_bytes_metadata():
    encoded = dumps({"receipt": receipt(), "blob": b"secret"})
    assert '"type":"bytes"' in encoded
    assert "secret" not in encoded


def test_serialization_pretty_mode():
    encoded = dumps({"a": 1}, pretty=True)
    assert "\n" in encoded


def test_serialization_rejects_unsupported_object():
    with pytest.raises(SerializationError):
        dumps(object())


def test_serialization_rejects_oversize_payload():
    with pytest.raises(SerializationError):
        dumps({"x": "y" * 100}, max_bytes=16)


def test_loads_object_requires_object_root():
    with pytest.raises(SerializationError):
        loads_object("[]")
    with pytest.raises(SerializationError):
        loads_object("not-json")


def test_receipt_round_trip_from_dict():
    original = receipt()
    restored = receipt_from_dict(original.to_dict())
    assert restored.command == original.command
    assert restored.receipt_id == original.receipt_id
    assert restored.duration_ms == original.duration_ms


def test_receipt_from_dict_rejects_missing_fields():
    with pytest.raises(SerializationError):
        receipt_from_dict({"command": "python"})
