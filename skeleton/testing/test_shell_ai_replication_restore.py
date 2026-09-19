"""Exact-prefix restore tests for durable journal and receipt replication."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalConflict,
    DistributedJournalCorruption,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def journal_with_events(
    count: int,
    *,
    namespace: str = "journal",
):
    backend = InMemoryFencedStore()
    now = {"value": 1.0}

    def clock():
        value = now["value"]
        now["value"] += 1.0
        return value

    journal = DistributedAIDecisionJournal(
        backend,
        namespace=namespace,
        clock=clock,
    )
    events = []
    for index in range(1, count + 1):
        events.append(
            journal.append(
                f"event.{index}",
                session_id=f"session-{index % 2}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
                data={"index": index},
            )
        )
    return backend, journal, tuple(events)


def make_receipt(
    index: int,
    *,
    receipt_id: str | None = None,
    fingerprint: str | None = None,
    correlation_id: str | None = None,
    attempt: int = 1,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=(
            correlation_id
            if correlation_id is not None
            else f"corr-{index}"
        ),
        fingerprint=(
            fingerprint
            if fingerprint is not None
            else fp(hex(index % 16)[2:])
        ),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index,
        stderr_bytes=0,
        attempt=attempt,
        receipt_id=(
            receipt_id
            if receipt_id is not None
            else f"receipt-{index}"
        ),
        metadata={"index": index},
    )


def receipt_chain_with_items(
    count: int,
    *,
    namespace: str = "receipts",
):
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace=namespace,
    )
    items = []
    for index in range(1, count + 1):
        items.append(
            chain.append(
                make_receipt(index)
            )
        )
    return backend, chain, tuple(items)


def test_journal_restore_bootstraps_empty_target():
    _, source, events = journal_with_events(5)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    head = target.restore_segment(events)
    assert head.sequence == 5
    assert head.root_hash == events[-1].event_hash
    assert target.snapshot() == events
    assert target.verify()


def test_journal_restore_partial_target():
    _, _, events = journal_with_events(5)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment(events[:2])
    assert target.length() == 2
    target.restore_segment(events[2:])
    assert target.snapshot() == events
    assert target.verify()


def test_journal_restore_full_segment_is_idempotent():
    _, _, events = journal_with_events(4)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    first = target.restore_segment(events)
    second = target.restore_segment(events)
    assert second == first
    assert target.length() == 4
    assert target.snapshot() == events


def test_journal_restore_old_prefix_when_target_ahead_is_idempotent():
    _, _, events = journal_with_events(5)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment(events)
    head = target.restore_segment(events[:2])
    assert head.sequence == 5
    assert target.snapshot() == events


def test_journal_restore_rejects_same_sequence_divergence():
    _, _, source_events = journal_with_events(3)
    _, divergent, _ = journal_with_events(
        1,
        namespace="other",
    )
    divergent_event = divergent.append(
        "different",
        session_id="different",
        intent_id="different",
        proposal_id="different",
        summary="different",
    )
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment((divergent_event,))
    before = target.head()
    with pytest.raises(
        DistributedJournalConflict,
        match="diverges",
    ):
        target.restore_segment(source_events)
    assert target.head() == before


def test_journal_restore_rejects_gap_from_empty_target():
    _, _, events = journal_with_events(4)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedJournalConflict,
        match="sequence gap",
    ):
        target.restore_segment(events[2:])
    assert target.length() == 0


def test_journal_restore_rejects_broken_digest_before_mutation():
    _, _, events = journal_with_events(2)
    broken = replace(
        events[0],
        event_hash=fp("f"),
    )
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="digest",
    ):
        target.restore_segment(
            (broken, events[1])
        )
    assert target.length() == 0


def test_journal_restore_rejects_broken_linkage_before_mutation():
    _, _, events = journal_with_events(2)
    broken = replace(
        events[1],
        previous_hash=fp("f"),
    )
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="linkage",
    ):
        target.restore_segment(
            (events[0], broken)
        )
    assert target.length() == 0


def test_journal_restore_rejects_noncontiguous_sequence():
    _, _, events = journal_with_events(3)
    broken = replace(
        events[1],
        sequence=99,
    )
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="sequence",
    ):
        target.restore_segment(
            (events[0], broken)
        )
    assert target.length() == 0


def test_journal_restore_rejects_wrong_item_type():
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        TypeError,
        match="AIDecisionEvent",
    ):
        target.restore_segment((object(),))


def test_journal_restore_enforces_batch_bound():
    _, _, events = journal_with_events(3)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedJournalConflict,
        match="bounded",
    ):
        target.restore_segment(
            events,
            max_items=2,
        )
    assert target.length() == 0


@pytest.mark.parametrize("max_items", [0, -1, True, 1.2])
def test_journal_restore_validates_batch_bound(max_items):
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(ValueError, match="max_items"):
        target.restore_segment(
            (),
            max_items=max_items,
        )


def test_journal_restore_enforces_target_capacity():
    _, _, events = journal_with_events(3)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
        max_events=2,
    )
    with pytest.raises(
        DistributedJournalConflict,
        match="capacity",
    ):
        target.restore_segment(events)
    assert target.length() == 0


def test_journal_restore_populates_sequence_indexes():
    _, _, events = journal_with_events(4)
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment(events)
    for sequence, event in enumerate(
        events,
        start=1,
    ):
        assert (
            target.get_by_sequence(
                sequence,
                repair_missing=False,
            )
            == event
        )


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflicted = False

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
            and not self.conflicted
        ):
            self.conflicted = True
            raise DistributedStateConflict(
                "synthetic conflict"
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


def test_journal_restore_retries_transient_cas_conflict():
    _, _, events = journal_with_events(2)
    target = DistributedAIDecisionJournal(
        ConflictOnceBackend(),
        namespace="target",
    )
    target.restore_segment(events)
    assert target.snapshot() == events
    assert target.verify()


class CommitThenConflictJournalBackend(ConflictOnceBackend):
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
            and not self.conflicted
        ):
            self.conflicted = True
            self.store.compare_and_swap(
                namespace,
                key,
                expected_revision=expected_revision,
                value=value,
            )
            raise DistributedStateConflict(
                "commit happened before response loss"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_journal_restore_recovers_lost_success_response():
    _, _, events = journal_with_events(2)
    target = DistributedAIDecisionJournal(
        CommitThenConflictJournalBackend(),
        namespace="target",
    )
    target.restore_segment(events)
    assert target.snapshot() == events
    assert target.verify()


def test_empty_journal_restore_is_noop():
    target = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="target",
    )
    before = target.head()
    after = target.restore_segment(())
    assert after == before


def test_receipt_restore_bootstraps_empty_target():
    _, source, items = receipt_chain_with_items(5)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    head = target.restore_segment(items)
    assert head.sequence == 5
    assert head.root_hash == items[-1].receipt_hash
    assert target.snapshot() == items
    assert target.verify()
    assert source.root_hash() == target.root_hash()


def test_receipt_restore_partial_target():
    _, _, items = receipt_chain_with_items(5)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment(items[:2])
    target.restore_segment(items[2:])
    assert target.snapshot() == items
    assert target.verify()


def test_receipt_restore_is_idempotent():
    _, _, items = receipt_chain_with_items(4)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    first = target.restore_segment(items)
    second = target.restore_segment(items)
    assert second == first
    assert target.length() == 4


def test_receipt_restore_old_prefix_when_target_ahead():
    _, _, items = receipt_chain_with_items(5)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment(items)
    target.restore_segment(items[:2])
    assert target.snapshot() == items


def test_receipt_restore_rejects_gap():
    _, _, items = receipt_chain_with_items(4)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="sequence gap",
    ):
        target.restore_segment(items[2:])
    assert target.length() == 0


def test_receipt_restore_rejects_broken_digest_before_mutation():
    _, _, items = receipt_chain_with_items(2)
    broken = replace(
        items[0],
        receipt_hash=fp("f"),
    )
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="digest",
    ):
        target.restore_segment(
            (broken, items[1])
        )
    assert target.length() == 0


def test_receipt_restore_rejects_linkage_mismatch():
    _, _, items = receipt_chain_with_items(2)
    broken = replace(
        items[1],
        previous_hash=fp("f"),
    )
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="linkage",
    ):
        target.restore_segment(
            (items[0], broken)
        )
    assert target.length() == 0


def test_receipt_restore_rejects_wrong_type():
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        TypeError,
        match="ChainedReceipt",
    ):
        target.restore_segment((object(),))


def test_receipt_restore_batch_bound():
    _, _, items = receipt_chain_with_items(3)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="bounded",
    ):
        target.restore_segment(
            items,
            max_items=2,
        )
    assert target.length() == 0


@pytest.mark.parametrize("max_items", [0, -1, True, 1.2])
def test_receipt_restore_validates_batch_bound(max_items):
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(ValueError, match="max_items"):
        target.restore_segment(
            (),
            max_items=max_items,
        )


def test_receipt_restore_enforces_capacity():
    _, _, items = receipt_chain_with_items(3)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
        max_receipts=2,
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="capacity",
    ):
        target.restore_segment(items)
    assert target.length() == 0


def test_receipt_restore_builds_sequence_and_id_indexes():
    _, _, items = receipt_chain_with_items(4)
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    target.restore_segment(items)
    for sequence, item in enumerate(
        items,
        start=1,
    ):
        assert (
            target.get_by_sequence(
                sequence,
                repair_missing=False,
            )
            == item
        )
        inclusion = target.require_receipt(
            item.receipt.receipt_id,
            fingerprint=item.receipt.fingerprint,
        )
        assert inclusion.committed
        assert inclusion.node == item


def test_receipt_restore_rejects_existing_receipt_id_collision_before_head_change():
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    existing = target.append(
        make_receipt(
            1,
            receipt_id="shared",
            fingerprint=fp("a"),
        )
    )

    source = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="source",
    )
    source.append(
        make_receipt(
            1,
            receipt_id="other",
            fingerprint=fp("a"),
        )
    )
    colliding = source.append(
        make_receipt(
            2,
            receipt_id="shared",
            fingerprint=fp("b"),
        )
    )
    before = target.head()
    with pytest.raises(
        DistributedReceiptConflict,
        match="receipt_id",
    ):
        target.restore_segment((colliding,))
    assert target.head() == before
    assert target.snapshot() == (existing,)


def test_receipt_restore_rejects_duplicate_id_inside_segment_before_mutation():
    source = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="source",
    )
    first = source.append(
        make_receipt(
            1,
            receipt_id="duplicate",
            fingerprint=fp("a"),
        )
    )
    # Construct a self-consistent second node with the same semantic id.
    second_receipt = make_receipt(
        2,
        receipt_id="duplicate",
        fingerprint=fp("b"),
    )
    from skeleton.shells.receipts import (
        ChainedReceipt,
        ReceiptChain,
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
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="reuses receipt_id",
    ):
        target.restore_segment(
            (first, second)
        )
    assert target.length() == 0


def test_receipt_restore_retries_transient_cas_conflict():
    _, _, items = receipt_chain_with_items(2)
    target = DistributedReceiptChain(
        ConflictOnceBackend(),
        namespace="target",
    )
    target.restore_segment(items)
    assert target.snapshot() == items
    assert target.verify()


class CommitThenConflictReceiptBackend(ConflictOnceBackend):
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
            and not self.conflicted
        ):
            self.conflicted = True
            self.store.compare_and_swap(
                namespace,
                key,
                expected_revision=expected_revision,
                value=value,
            )
            raise DistributedStateConflict(
                "receipt commit response lost"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_receipt_restore_recovers_lost_success_response():
    _, _, items = receipt_chain_with_items(2)
    target = DistributedReceiptChain(
        CommitThenConflictReceiptBackend(),
        namespace="target",
    )
    target.restore_segment(items)
    assert target.snapshot() == items
    assert target.verify()


def test_empty_receipt_restore_is_noop():
    target = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="target",
    )
    before = target.head()
    after = target.restore_segment(())
    assert after == before


def test_receipt_restore_existing_prefix_repairs_deleted_indexes():
    backend = InMemoryFencedStore()
    target = DistributedReceiptChain(
        backend,
        namespace="target",
    )
    _, _, items = receipt_chain_with_items(2)
    target.restore_segment(items)

    sequence_key = target._sequence_key(1)
    receipt_key = target._index_key(
        items[0].receipt.receipt_id
    )
    sequence_record = backend.get(
        "target",
        sequence_key,
    )
    receipt_record = backend.get(
        "target",
        receipt_key,
    )
    backend.delete(
        "target",
        sequence_key,
        expected_revision=sequence_record.revision,
    )
    backend.delete(
        "target",
        receipt_key,
        expected_revision=receipt_record.revision,
    )

    target.restore_segment(items[:1])
    assert (
        target.get_by_sequence(
            1,
            repair_missing=False,
        )
        == items[0]
    )
    assert (
        target.require_receipt(
            items[0].receipt.receipt_id
        ).node
        == items[0]
    )


def test_journal_restore_existing_prefix_repairs_deleted_sequence_index():
    backend = InMemoryFencedStore()
    target = DistributedAIDecisionJournal(
        backend,
        namespace="target",
    )
    _, _, events = journal_with_events(2)
    target.restore_segment(events)
    key = target._sequence_key(1)
    record = backend.get("target", key)
    backend.delete(
        "target",
        key,
        expected_revision=record.revision,
    )
    target.restore_segment(events[:1])
    assert (
        target.get_by_sequence(
            1,
            repair_missing=False,
        )
        == events[0]
    )
