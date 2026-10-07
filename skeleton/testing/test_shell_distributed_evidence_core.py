"""Focused non-AI evidence integrity regressions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    GENESIS_HASH as EVIDENCE_GENESIS,
)
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.state_conflicts import DistributedStateConflict


@dataclass(frozen=True)
class _Record:
    revision: int
    value: object


class _MemoryCAS:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], _Record] = {}

    def get(self, namespace: str, key: str):
        return self._items.get((namespace, key))

    def put_if_absent(self, namespace: str, key: str, value: object):
        item = (namespace, key)
        if item in self._items:
            raise DistributedStateConflict("key already exists")
        record = _Record(1, value)
        self._items[item] = record
        return record

    def compare_and_swap(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
        value: object,
    ):
        item = (namespace, key)
        current = self._items.get(item)
        if current is None:
            if expected_revision != 0:
                raise DistributedStateConflict("revision mismatch")
            record = _Record(1, value)
            self._items[item] = record
            return record
        if current.revision != expected_revision:
            raise DistributedStateConflict("revision mismatch")
        record = _Record(current.revision + 1, value)
        self._items[item] = record
        return record

    def delete(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
    ) -> bool:
        item = (namespace, key)
        current = self._items.get(item)
        if current is None:
            return False
        if current.revision != expected_revision:
            raise DistributedStateConflict("revision mismatch")
        del self._items[item]
        return True


def _receipt(receipt_id: str = "receipt-1") -> ExecutionReceipt:
    now = datetime.now(timezone.utc).isoformat()
    return ExecutionReceipt(
        command="python",
        correlation_id="corr",
        fingerprint="f" * 64,
        started_at=now,
        finished_at=now,
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=3,
        stderr_bytes=0,
        receipt_id=receipt_id,
        metadata={"kind": "test"},
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_evidence_chain_rejects_invalid_capacity(value):
    with pytest.raises(ValueError, match="max_events"):
        ContentAddressedEvidenceChain(_MemoryCAS(), namespace="e", max_events=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_evidence_chain_rejects_invalid_cas_retries(value):
    with pytest.raises(ValueError, match="max_cas_retries"):
        ContentAddressedEvidenceChain(
            _MemoryCAS(),
            namespace="e",
            max_cas_retries=value,
        )


def test_evidence_chain_empty_root_is_genesis():
    chain = ContentAddressedEvidenceChain(_MemoryCAS(), namespace="e")
    assert chain.length() == 0
    assert chain.root_hash() == EVIDENCE_GENESIS
    assert chain.snapshot() == ()
    assert chain.verify()


def test_evidence_chain_append_is_ordered_and_verifiable():
    chain = ContentAddressedEvidenceChain(_MemoryCAS(), namespace="e")
    first = chain.append("event", {"n": 1})
    second = chain.append("event", {"n": 2})
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.node_hash
    assert [node.payload["n"] for node in chain.snapshot()] == [1, 2]
    assert chain.root_hash() == second.node_hash
    assert chain.verify()


def test_evidence_digest_is_canonical():
    left = ContentAddressedEvidenceChain.node_digest(
        EVIDENCE_GENESIS,
        1,
        "event",
        {"b": 2, "a": 1},
    )
    right = ContentAddressedEvidenceChain.node_digest(
        EVIDENCE_GENESIS,
        1,
        "event",
        {"a": 1, "b": 2},
    )
    assert left == right
    assert len(left) == 64


def test_distributed_receipt_chain_empty_is_compatible_with_local_chain():
    chain = DistributedReceiptChain(_MemoryCAS(), namespace="r")
    assert chain.length() == 0
    assert chain.root_hash() == ReceiptChain.GENESIS
    assert chain.snapshot() == ()
    assert chain.verify()


def test_distributed_receipt_round_trip_and_sequence_index():
    chain = DistributedReceiptChain(_MemoryCAS(), namespace="r")
    receipt = _receipt()
    node = chain.append(receipt)
    assert node.sequence == 1
    assert chain.length() == 1
    assert chain.root_hash() == node.receipt_hash
    assert chain.get_by_sequence(1) == node
    assert chain.require_receipt(receipt.receipt_id).node == node
    assert chain.verify()


def test_distributed_receipt_append_is_idempotent_by_receipt_id():
    chain = DistributedReceiptChain(_MemoryCAS(), namespace="r")
    receipt = _receipt()
    first = chain.append(receipt)
    second = chain.append(receipt)
    assert second == first
    assert chain.length() == 1
    assert chain.snapshot() == (first,)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_distributed_receipts_reject_invalid_capacity(value):
    with pytest.raises(ValueError, match="max_receipts"):
        DistributedReceiptChain(_MemoryCAS(), namespace="r", max_receipts=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2", 129])
def test_distributed_receipts_reject_invalid_retry_budget(value):
    with pytest.raises(ValueError, match="max_cas_retries"):
        DistributedReceiptChain(
            _MemoryCAS(),
            namespace="r",
            max_cas_retries=value,
        )
