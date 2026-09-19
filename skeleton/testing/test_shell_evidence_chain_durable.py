"""Durable content-addressed evidence and receipt chain tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.durable_receipts import DistributedReceiptChain
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceConflict,
    EvidenceCorruption,
    EvidenceHead,
    EvidenceNode,
    GENESIS_HASH,
)
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain


def receipt(command="python", correlation="c", fingerprint="f" * 64):
    now = datetime.now(timezone.utc).isoformat()
    return ExecutionReceipt(
        command=command,
        correlation_id=correlation,
        fingerprint=fingerprint,
        started_at=now,
        finished_at=now,
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=3,
        stderr_bytes=0,
        metadata={"kind": "test"},
    )


def test_empty_evidence_chain_uses_genesis():
    chain = ContentAddressedEvidenceChain(
        InMemoryFencedStore(),
        namespace="evidence",
    )
    assert chain.length() == 0
    assert chain.root_hash() == GENESIS_HASH
    assert chain.snapshot() == ()
    assert chain.verify()


def test_evidence_append_sequence_and_previous_hash():
    chain = ContentAddressedEvidenceChain(
        InMemoryFencedStore(),
        namespace="evidence",
    )
    first = chain.append("one", {"value": 1})
    second = chain.append("two", {"value": 2})
    assert first.sequence == 1
    assert first.previous_hash == GENESIS_HASH
    assert second.sequence == 2
    assert second.previous_hash == first.node_hash
    assert chain.root_hash() == second.node_hash
    assert chain.verify()


def test_evidence_digest_is_deterministic():
    digest = ContentAddressedEvidenceChain.node_digest(
        GENESIS_HASH,
        1,
        "event",
        {"b": 2, "a": 1},
    )
    same = ContentAddressedEvidenceChain.node_digest(
        GENESIS_HASH,
        1,
        "event",
        {"a": 1, "b": 2},
    )
    assert digest == same
    assert len(digest) == 64


def test_evidence_snapshot_reconstructs_forward_order():
    chain = ContentAddressedEvidenceChain(
        InMemoryFencedStore(),
        namespace="evidence",
    )
    for index in range(5):
        chain.append("event", {"index": index})
    items = chain.snapshot()
    assert [item.sequence for item in items] == [1, 2, 3, 4, 5]
    assert [item.payload["index"] for item in items] == [0, 1, 2, 3, 4]


def test_evidence_capacity_is_enforced():
    chain = ContentAddressedEvidenceChain(
        InMemoryFencedStore(),
        namespace="evidence",
        max_events=1,
    )
    chain.append("one", {})
    with pytest.raises(RuntimeError, match="capacity"):
        chain.append("two", {})


def test_evidence_node_payload_is_immutable():
    node = EvidenceNode(
        1,
        GENESIS_HASH,
        "a" * 64,
        "event",
        {"x": 1},
    )
    with pytest.raises(TypeError):
        node.payload["x"] = 2


def test_evidence_invalid_empty_head():
    with pytest.raises(ValueError):
        EvidenceHead(0, "a" * 64)


def test_evidence_invalid_nonempty_genesis_head():
    with pytest.raises(ValueError):
        EvidenceHead(1, GENESIS_HASH)


def test_evidence_missing_committed_node_detected():
    store = InMemoryFencedStore()
    chain = ContentAddressedEvidenceChain(store, namespace="evidence")
    node = chain.append("event", {"x": 1})
    node_record = store.get("evidence", f"node:{node.node_hash}")
    assert node_record is not None
    store.delete(
        "evidence",
        f"node:{node.node_hash}",
        expected_revision=node_record.revision,
    )
    with pytest.raises(EvidenceCorruption, match="missing"):
        chain.snapshot()
    assert not chain.verify()


def test_evidence_tampered_node_detected():
    store = InMemoryFencedStore()
    chain = ContentAddressedEvidenceChain(store, namespace="evidence")
    node = chain.append("event", {"x": 1})
    record = store.get("evidence", f"node:{node.node_hash}")
    tampered = replace(node, payload={"x": 2})
    store.compare_and_swap(
        "evidence",
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=tampered,
    )
    assert not chain.verify()


def test_evidence_tampered_head_type_detected():
    store = InMemoryFencedStore()
    chain = ContentAddressedEvidenceChain(store, namespace="evidence")
    chain.append("event", {"x": 1})
    record = store.get("evidence", "head")
    store.compare_and_swap(
        "evidence",
        "head",
        expected_revision=record.revision,
        value={"bad": "head"},
    )
    with pytest.raises(EvidenceCorruption):
        chain.head()


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflicted = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(self, namespace, key, *, expected_revision, value):
        if key == "head" and not self.conflicted:
            self.conflicted = True
            other = EvidenceHead(1, "1" * 64)
            if expected_revision == 0:
                self.store.put_if_absent(namespace, key, other)
            else:
                self.store.compare_and_swap(
                    namespace,
                    key,
                    expected_revision=expected_revision,
                    value=other,
                )
            raise DistributedStateConflict("simulated concurrent writer")
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_evidence_cas_conflict_retries_against_new_head():
    backend = ConflictOnceBackend()
    chain = ContentAddressedEvidenceChain(
        backend,
        namespace="evidence",
    )
    # The injected head refers to a node that does not exist, so a later
    # snapshot is corrupt, but append must observe the changed head rather than
    # misreporting the CAS race as a backend outage.
    node = chain.append("event", {"x": 1})
    assert node.sequence == 2
    assert node.previous_hash == "1" * 64


class BrokenCASBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(self, namespace, key, *, expected_revision, value):
        raise OSError("backend unavailable")


def test_evidence_backend_outage_is_not_hidden_as_conflict():
    chain = ContentAddressedEvidenceChain(
        BrokenCASBackend(),
        namespace="evidence",
    )
    with pytest.raises(OSError, match="unavailable"):
        chain.append("event", {"x": 1})


def test_durable_receipt_chain_empty_compatible_root():
    chain = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="receipts",
    )
    assert chain.root_hash() == ReceiptChain.GENESIS
    assert chain.snapshot() == ()
    assert chain.verify()


def test_durable_receipt_append_round_trip():
    store = InMemoryFencedStore()
    chain = DistributedReceiptChain(store, namespace="receipts")
    source = receipt()
    item = chain.append(source)
    assert item.sequence == 1
    assert item.receipt == source
    assert item.previous_hash == ReceiptChain.GENESIS
    assert chain.root_hash() == item.receipt_hash
    assert chain.verify()


def test_durable_receipts_survive_new_facade_instance():
    store = InMemoryFencedStore()
    first = DistributedReceiptChain(store, namespace="receipts")
    one = first.append(receipt(correlation="one"))
    second = DistributedReceiptChain(store, namespace="receipts")
    two = second.append(receipt(correlation="two"))
    assert [item.receipt.correlation_id for item in second.snapshot()] == [
        "one",
        "two",
    ]
    assert two.previous_hash == one.receipt_hash
    assert second.verify()


def test_durable_receipt_hash_matches_in_process_semantics():
    store = InMemoryFencedStore()
    durable = DistributedReceiptChain(store, namespace="receipts")
    local = ReceiptChain()
    source = receipt()
    durable_item = durable.append(source)
    local_item = local.append(source)
    assert durable_item.receipt_hash == local_item.receipt_hash
    assert durable.root_hash() == local.root_hash()


def test_durable_receipt_multiple_hashes_match_local_chain():
    store = InMemoryFencedStore()
    durable = DistributedReceiptChain(store, namespace="receipts")
    local = ReceiptChain()
    for index in range(4):
        source = receipt(correlation=f"c{index}")
        durable.append(source)
        local.append(source)
    assert [item.receipt_hash for item in durable.snapshot()] == [
        item.receipt_hash for item in local.snapshot()
    ]
    assert durable.root_hash() == local.root_hash()


def test_durable_receipt_outer_node_tamper_fails_verify():
    store = InMemoryFencedStore()
    durable = DistributedReceiptChain(store, namespace="receipts")
    outer = durable.append(receipt())
    key = durable._node_key(outer.receipt_hash)
    record = store.get("receipts", key)
    store.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=replace(
            outer,
            receipt=replace(
                outer.receipt,
                stdout_bytes=outer.receipt.stdout_bytes + 1,
            ),
        ),
    )
    assert not durable.verify()


def test_durable_receipt_capacity():
    durable = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="receipts",
        max_receipts=1,
    )
    durable.append(receipt())
    with pytest.raises(RuntimeError):
        durable.append(receipt(correlation="two"))
