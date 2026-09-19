"""Distributed receipt chain concurrency, recovery, and corruption tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    DistributedReceiptHead,
    GENESIS_HASH,
    ReceiptInclusion,
    ReceiptIndexEntry,
)
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


def fp(char: str) -> str:
    return char * 64


def receipt(
    name: str,
    *,
    receipt_id: str | None = None,
    fingerprint: str | None = None,
    correlation_id: str = "correlation",
    attempt: int = 1,
    returncode: int | None = 0,
    ok: bool = True,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=correlation_id,
        fingerprint=fingerprint or fp("a"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=returncode,
        ok=ok,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=attempt,
        receipt_id=receipt_id or f"receipt-{name}",
        metadata={"name": name},
    )


def test_empty_distributed_receipt_chain():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    assert chain.snapshot() == ()
    assert chain.length() == 0
    assert chain.root_hash() == GENESIS_HASH
    assert chain.verify()
    assert chain.head() == DistributedReceiptHead(
        0,
        GENESIS_HASH,
    )


def test_append_uses_existing_receipt_hash_contract():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    value = receipt("one")
    item = chain.append(value)
    expected = ReceiptChain._hash(
        GENESIS_HASH,
        1,
        value,
    )
    assert item.receipt_hash == expected
    assert item.previous_hash == GENESIS_HASH
    assert item.sequence == 1
    assert chain.root_hash() == expected
    assert chain.verify()


def test_multiple_receipts_are_contiguous():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    one = chain.append(receipt("one"))
    two = chain.append(
        receipt(
            "two",
            correlation_id="other",
        )
    )
    three = chain.append(
        receipt(
            "three",
            correlation_id="third",
        )
    )
    assert chain.snapshot() == (
        one,
        two,
        three,
    )
    assert two.previous_hash == one.receipt_hash
    assert three.previous_hash == two.receipt_hash
    assert chain.head().sequence == 3
    assert chain.verify()


def test_fresh_reader_observes_same_receipts():
    backend = InMemoryFencedStore()
    writer = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    one = writer.append(receipt("one"))
    two = writer.append(receipt("two"))

    reader = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    assert reader.snapshot() == (one, two)
    assert reader.root_hash() == writer.root_hash()
    assert reader.verify()


def test_receipt_id_index_is_written():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    value = receipt("indexed")
    item = chain.append(value)
    inclusion = chain.find_by_receipt_id(
        value.receipt_id
    )
    assert inclusion is not None
    assert inclusion.committed
    assert inclusion.node == item
    assert (
        inclusion.entry.receipt_fingerprint
        == value.fingerprint
    )


def test_append_same_receipt_is_idempotent():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    value = receipt("same")
    first = chain.append(value)
    second = chain.append(value)
    assert second == first
    assert chain.length() == 1
    assert chain.snapshot() == (first,)


def test_same_receipt_id_with_different_content_is_rejected():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    first = receipt(
        "first",
        receipt_id="shared",
        fingerprint=fp("a"),
    )
    second = receipt(
        "second",
        receipt_id="shared",
        fingerprint=fp("b"),
    )
    chain.append(first)
    with pytest.raises(
        DistributedReceiptConflict,
        match="different receipt content",
    ):
        chain.append(second)


def test_require_receipt_checks_fingerprint():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    value = receipt(
        "one",
        fingerprint=fp("a"),
    )
    chain.append(value)
    inclusion = chain.require_receipt(
        value.receipt_id,
        fingerprint=fp("a"),
    )
    assert inclusion.node.receipt == value
    with pytest.raises(
        DistributedReceiptConflict,
        match="fingerprint",
    ):
        chain.require_receipt(
            value.receipt_id,
            fingerprint=fp("b"),
        )


def test_require_missing_receipt():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="missing",
    ):
        chain.require_receipt("receipt-missing")


def test_require_receipts_preserves_request_order():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    one = receipt("one")
    two = receipt("two")
    chain.append(one)
    chain.append(two)
    inclusions = chain.require_receipts(
        (two.receipt_id, one.receipt_id)
    )
    assert [
        item.entry.receipt_id
        for item in inclusions
    ] == [two.receipt_id, one.receipt_id]


def test_require_receipts_rejects_duplicate_request():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    value = receipt("one")
    chain.append(value)
    with pytest.raises(
        DistributedReceiptConflict,
        match="duplicate",
    ):
        chain.require_receipts(
            (value.receipt_id, value.receipt_id)
        )


def test_index_self_heals_after_post_head_crash_window():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    value = receipt("heal")
    item = chain.append(value)
    index_key = chain._index_key(
        value.receipt_id
    )
    index_record = backend.get(
        "receipts",
        index_key,
    )
    assert index_record is not None
    backend.delete(
        "receipts",
        index_key,
        expected_revision=index_record.revision,
    )

    fresh = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    inclusion = fresh.find_by_receipt_id(
        value.receipt_id
    )
    assert inclusion is not None
    assert inclusion.committed
    assert inclusion.node == item
    assert backend.get(
        "receipts",
        index_key,
    ) is not None


def test_append_after_missing_index_does_not_duplicate_receipt():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    value = receipt("retry")
    first = chain.append(value)
    index_key = chain._index_key(
        value.receipt_id
    )
    index_record = backend.get(
        "receipts",
        index_key,
    )
    backend.delete(
        "receipts",
        index_key,
        expected_revision=index_record.revision,
    )

    fresh = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    second = fresh.append(value)
    assert second == first
    assert fresh.length() == 1


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_namespace_validation(namespace):
    with pytest.raises(ValueError, match="namespace"):
        DistributedReceiptChain(
            InMemoryFencedStore(),
            namespace=namespace,
        )


@pytest.mark.parametrize(
    "maximum",
    [0, -1, True, 1.2],
)
def test_max_receipts_validation(maximum):
    with pytest.raises(ValueError, match="max_receipts"):
        DistributedReceiptChain(
            InMemoryFencedStore(),
            max_receipts=maximum,
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True, 1.2],
)
def test_retry_bound_validation(retries):
    with pytest.raises(ValueError, match="max_cas_retries"):
        DistributedReceiptChain(
            InMemoryFencedStore(),
            max_cas_retries=retries,
        )


def test_capacity_exhaustion():
    chain = DistributedReceiptChain(
        InMemoryFencedStore(),
        max_receipts=1,
    )
    chain.append(receipt("one"))
    with pytest.raises(RuntimeError, match="capacity"):
        chain.append(receipt("two"))


def test_append_rejects_non_receipt():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(TypeError, match="ExecutionReceipt"):
        chain.append(object())


@pytest.mark.parametrize(
    "receipt_id",
    ["", "x" * 129],
)
def test_index_key_validates_receipt_id(receipt_id):
    with pytest.raises(ValueError, match="receipt_id"):
        DistributedReceiptChain._index_key(
            receipt_id
        )


def test_node_key_validates_hash():
    with pytest.raises(ValueError, match="SHA-256"):
        DistributedReceiptChain._node_key("bad")


def test_head_validation():
    with pytest.raises(ValueError):
        DistributedReceiptHead(-1, GENESIS_HASH)
    with pytest.raises(ValueError):
        DistributedReceiptHead(0, "a" * 64)
    with pytest.raises(ValueError):
        DistributedReceiptHead(1, GENESIS_HASH)
    with pytest.raises(ValueError):
        DistributedReceiptHead(1, "bad")


def test_index_entry_validation():
    with pytest.raises(ValueError):
        ReceiptIndexEntry(
            "",
            fp("a"),
            fp("b"),
            1,
        )
    with pytest.raises(ValueError):
        ReceiptIndexEntry(
            "id",
            "bad",
            fp("b"),
            1,
        )
    with pytest.raises(ValueError):
        ReceiptIndexEntry(
            "id",
            fp("a"),
            "bad",
            1,
        )
    with pytest.raises(ValueError):
        ReceiptIndexEntry(
            "id",
            fp("a"),
            fp("b"),
            0,
        )


def test_inclusion_validation():
    value = receipt("one")
    node_hash = ReceiptChain._hash(
        GENESIS_HASH,
        1,
        value,
    )
    node = ChainedReceipt(
        1,
        GENESIS_HASH,
        node_hash,
        value,
    )
    entry = ReceiptIndexEntry(
        value.receipt_id,
        node_hash,
        value.fingerprint,
        1,
    )
    inclusion = ReceiptInclusion(
        entry,
        node,
        True,
    )
    assert inclusion.to_dict()["committed"] is True

    with pytest.raises(ValueError, match="hash"):
        ReceiptInclusion(
            replace(
                entry,
                receipt_hash=fp("f"),
            ),
            node,
            True,
        )


def test_wrong_head_type_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "receipts",
        "head",
        {"bad": True},
    )
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="head",
    ):
        chain.head()
    assert not chain.verify()


def test_missing_committed_node_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "receipts",
        "head",
        DistributedReceiptHead(
            1,
            fp("f"),
        ),
    )
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="missing",
    ):
        chain.snapshot()
    assert not chain.verify()


def test_wrong_node_type_is_corruption():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "receipts",
        "node:" + fp("a"),
        {"bad": True},
    )
    backend.put_if_absent(
        "receipts",
        "head",
        DistributedReceiptHead(
            1,
            fp("a"),
        ),
    )
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="value type",
    ):
        chain.snapshot()


def test_receipt_node_tamper_breaks_verification():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    item = chain.append(receipt("one"))
    key = chain._node_key(
        item.receipt_hash
    )
    record = backend.get("receipts", key)
    tampered = replace(
        item,
        receipt=replace(
            item.receipt,
            stdout_bytes=99,
        ),
    )
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    assert not chain.verify()
    with pytest.raises(
        DistributedReceiptCorruption,
        match="digest",
    ):
        chain.snapshot()


def test_wrong_index_type_is_corruption():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    value = receipt("one")
    backend.put_if_absent(
        "receipts",
        chain._index_key(value.receipt_id),
        {"bad": True},
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="index",
    ):
        chain.find_by_receipt_id(
            value.receipt_id
        )


def test_index_to_missing_node_is_corruption():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    entry = ReceiptIndexEntry(
        "receipt-one",
        fp("a"),
        fp("b"),
        1,
    )
    backend.put_if_absent(
        "receipts",
        chain._index_key(
            entry.receipt_id
        ),
        entry,
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="missing",
    ):
        chain.find_by_receipt_id(
            entry.receipt_id
        )


def test_duplicate_committed_receipt_id_is_detected_during_repair():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    first_receipt = receipt(
        "one",
        receipt_id="duplicate",
        fingerprint=fp("a"),
    )
    first = chain.append(first_receipt)

    index_key = chain._index_key(
        "duplicate"
    )
    index_record = backend.get(
        "receipts",
        index_key,
    )
    backend.delete(
        "receipts",
        index_key,
        expected_revision=index_record.revision,
    )

    second_receipt = replace(
        first_receipt,
        fingerprint=fp("b"),
    )
    second_hash = ReceiptChain._hash(
        first.receipt_hash,
        2,
        second_receipt,
    )
    second = ChainedReceipt(
        2,
        first.receipt_hash,
        second_hash,
        second_receipt,
    )
    backend.put_if_absent(
        "receipts",
        chain._node_key(second_hash),
        second,
    )
    head_record = backend.get(
        "receipts",
        "head",
    )
    backend.compare_and_swap(
        "receipts",
        "head",
        expected_revision=head_record.revision,
        value=DistributedReceiptHead(
            2,
            second_hash,
        ),
    )

    with pytest.raises(
        DistributedReceiptCorruption,
        match="multiple",
    ):
        chain.find_by_receipt_id(
            "duplicate"
        )


class CompetingReceiptBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.injected = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(
            namespace,
            key,
            value,
        )

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            key == "head"
            and not self.injected
            and expected_revision == 0
        ):
            self.injected = True
            competitor = receipt(
                "competitor",
                fingerprint=fp("c"),
                correlation_id="competitor",
            )
            digest = ReceiptChain._hash(
                GENESIS_HASH,
                1,
                competitor,
            )
            node = ChainedReceipt(
                1,
                GENESIS_HASH,
                digest,
                competitor,
            )
            self.store.put_if_absent(
                namespace,
                f"node:{digest}",
                node,
            )
            self.store.compare_and_swap(
                namespace,
                "head",
                expected_revision=0,
                value=DistributedReceiptHead(
                    1,
                    digest,
                ),
            )
            raise DistributedStateConflict(
                "synthetic receipt race"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_competing_receipt_writer_serializes_by_head():
    backend = CompetingReceiptBackend()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    ours = chain.append(
        receipt(
            "ours",
            fingerprint=fp("d"),
            correlation_id="ours",
        )
    )
    items = chain.snapshot()
    assert len(items) == 2
    assert (
        items[0].receipt.receipt_id
        == "receipt-competitor"
    )
    assert items[1] == ours
    assert ours.sequence == 2
    assert chain.verify()


def test_competing_writer_leaves_unreachable_candidate_node():
    backend = CompetingReceiptBackend()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    ours_receipt = receipt(
        "ours",
        fingerprint=fp("d"),
        correlation_id="ours",
    )
    committed = chain.append(
        ours_receipt
    )
    orphan_hash = ReceiptChain._hash(
        GENESIS_HASH,
        1,
        ours_receipt,
    )
    orphan = chain.get_node(
        orphan_hash
    )
    assert orphan.sequence == 1
    assert orphan.receipt_hash not in {
        item.receipt_hash
        for item in chain.snapshot()
    }
    assert committed.sequence == 2


def test_require_root_accepts_current_root():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    chain.append(receipt("one"))
    assert chain.require_root(
        chain.root_hash()
    ) == chain.head()


def test_require_root_rejects_wrong_root():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="differs",
    ):
        chain.require_root(fp("f"))


def test_namespace_isolation():
    backend = InMemoryFencedStore()
    first = DistributedReceiptChain(
        backend,
        namespace="first",
    )
    second = DistributedReceiptChain(
        backend,
        namespace="second",
    )
    first.append(receipt("first"))
    second.append(receipt("second"))
    assert first.length() == 1
    assert second.length() == 1
    assert (
        first.snapshot()[0].receipt.receipt_id
        == "receipt-first"
    )
    assert (
        second.snapshot()[0].receipt.receipt_id
        == "receipt-second"
    )


def test_head_to_dict():
    assert DistributedReceiptHead(
        3,
        fp("a"),
    ).to_dict() == {
        "sequence": 3,
        "root_hash": fp("a"),
    }


def test_index_to_dict():
    entry = ReceiptIndexEntry(
        "receipt",
        fp("a"),
        fp("b"),
        2,
    )
    assert entry.to_dict() == {
        "receipt_id": "receipt",
        "receipt_hash": fp("a"),
        "receipt_fingerprint": fp("b"),
        "sequence": 2,
    }
