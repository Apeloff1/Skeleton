"""Sequence-index acceleration and repair tests for durable shell chains."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalConflict,
    DistributedJournalCorruption,
    DistributedJournalIndexHealth,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    DistributedReceiptIndexHealth,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def append_events(
    journal: DistributedAIDecisionJournal,
    count: int,
    *,
    session_id: str = "session",
):
    return tuple(
        journal.append(
            f"event.{index}",
            session_id=session_id,
            intent_id="intent",
            proposal_id=f"proposal-{index}",
            summary=f"event {index}",
            data={"index": index},
        )
        for index in range(1, count + 1)
    )


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(chr(96 + ((index - 1) % 20) + 1)),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
        metadata={"index": index},
    )


def append_receipts(
    chain: DistributedReceiptChain,
    count: int,
):
    return tuple(
        chain.append(receipt(index))
        for index in range(1, count + 1)
    )


def test_journal_append_writes_sequence_index():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    event = append_events(journal, 1)[0]
    entry = journal._sequence_index(1)
    assert entry == DistributedJournalSequenceIndex(
        1,
        event.event_hash,
    )
    assert journal.get_by_sequence(1) == event
    assert journal.root_for_sequence(1) == event.event_hash


def test_receipt_append_writes_sequence_index():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    item = append_receipts(chain, 1)[0]
    entry = chain._sequence_index(1)
    assert entry == DistributedReceiptSequenceIndex(
        1,
        item.receipt_hash,
    )
    assert chain.get_by_sequence(1) == item
    assert chain.root_for_sequence(1) == item.receipt_hash


def test_journal_sequence_indexes_cover_all_committed_events():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    events = append_events(journal, 8)
    for index, event in enumerate(events, start=1):
        assert journal.get_by_sequence(index) == event
    health = journal.inspect_sequence_indexes()
    assert health.healthy
    assert health.head_sequence == 8
    assert health.inspected == 8
    assert health.indexed == 8
    assert health.missing == 0
    assert health.corrupt == 0


def test_receipt_sequence_indexes_cover_all_committed_nodes():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    items = append_receipts(chain, 8)
    for index, item in enumerate(items, start=1):
        assert chain.get_by_sequence(index) == item
    health = chain.inspect_sequence_indexes()
    assert health.healthy
    assert health.head_sequence == 8
    assert health.inspected == 8
    assert health.indexed == 8
    assert health.missing == 0
    assert health.corrupt == 0


def test_journal_genesis_root_for_sequence_zero():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    assert journal.root_for_sequence(0) == journal.GENESIS if hasattr(journal, "GENESIS") else journal.root_hash()


def test_receipt_genesis_root_for_sequence_zero():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    assert chain.root_for_sequence(0) == chain.root_hash()


@pytest.mark.parametrize("sequence", [-1, True, 1.5, "1"])
def test_journal_sequence_validation(sequence):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="sequence"):
        journal.get_by_sequence(sequence)


@pytest.mark.parametrize("sequence", [-1, True, 1.5, "1"])
def test_receipt_sequence_validation(sequence):
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="sequence"):
        chain.get_by_sequence(sequence)


def test_journal_sequence_beyond_head_is_rejected():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_events(journal, 2)
    with pytest.raises(IndexError, match="head"):
        journal.get_by_sequence(3)


def test_receipt_sequence_beyond_head_is_rejected():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    append_receipts(chain, 2)
    with pytest.raises(IndexError, match="head"):
        chain.get_by_sequence(3)


def test_journal_missing_index_self_heals_from_committed_chain():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(journal, 4)
    key = journal._sequence_key(2)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    assert journal.inspect_sequence_indexes().missing == 1
    recovered = journal.get_by_sequence(2)
    assert recovered == events[1]
    assert journal._sequence_index(2) is not None
    assert journal.inspect_sequence_indexes().healthy


def test_receipt_missing_index_self_heals_from_committed_chain():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(chain, 4)
    key = chain._sequence_key(2)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    assert chain.inspect_sequence_indexes().missing == 1
    recovered = chain.get_by_sequence(2)
    assert recovered == items[1]
    assert chain._sequence_index(2) is not None
    assert chain.inspect_sequence_indexes().healthy


def test_journal_missing_index_can_fail_without_repair():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_events(journal, 2)
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DistributedJournalConflict,
        match="index is missing",
    ):
        journal.get_by_sequence(
            1,
            repair_missing=False,
        )


def test_receipt_missing_index_can_fail_without_repair():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(chain, 2)
    key = chain._sequence_key(1)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DistributedReceiptConflict,
        match="index is missing",
    ):
        chain.get_by_sequence(
            1,
            repair_missing=False,
        )


def test_fresh_journal_reader_repairs_missing_index():
    backend = InMemoryFencedStore()
    writer = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(writer, 3)
    key = writer._sequence_key(1)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    fresh = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    assert fresh.get_by_sequence(1) == events[0]
    assert fresh.inspect_sequence_indexes().healthy


def test_fresh_receipt_reader_repairs_missing_index():
    backend = InMemoryFencedStore()
    writer = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(writer, 3)
    key = writer._sequence_key(1)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    fresh = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    assert fresh.get_by_sequence(1) == items[0]
    assert fresh.inspect_sequence_indexes().healthy


def test_journal_range_returns_exact_verified_window():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    events = append_events(journal, 10)
    assert journal.snapshot_range(3, 6) == events[2:6]


def test_receipt_range_returns_exact_verified_window():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    items = append_receipts(chain, 10)
    assert chain.snapshot_range(3, 6) == items[2:6]


def test_journal_single_item_range():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    events = append_events(journal, 5)
    assert journal.snapshot_range(4, 4) == (events[3],)


def test_receipt_single_item_range():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    items = append_receipts(chain, 5)
    assert chain.snapshot_range(4, 4) == (items[3],)


@pytest.mark.parametrize(
    "start,end",
    [
        (0, 1),
        (-1, 1),
        (2, 1),
        (True, 2),
        (1, True),
    ],
)
def test_journal_range_validation(start, end):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError):
        journal.snapshot_range(start, end)


@pytest.mark.parametrize(
    "start,end",
    [
        (0, 1),
        (-1, 1),
        (2, 1),
        (True, 2),
        (1, True),
    ],
)
def test_receipt_range_validation(start, end):
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError):
        chain.snapshot_range(start, end)


def test_journal_range_honors_bound():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_events(journal, 5)
    with pytest.raises(
        DistributedJournalConflict,
        match="bounded",
    ):
        journal.snapshot_range(
            1,
            5,
            max_items=4,
        )


def test_receipt_range_honors_bound():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    append_receipts(chain, 5)
    with pytest.raises(
        DistributedReceiptConflict,
        match="bounded",
    ):
        chain.snapshot_range(
            1,
            5,
            max_items=4,
        )


def test_journal_range_beyond_head_is_rejected():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_events(journal, 3)
    with pytest.raises(IndexError, match="head"):
        journal.snapshot_range(2, 4)


def test_receipt_range_beyond_head_is_rejected():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    append_receipts(chain, 3)
    with pytest.raises(IndexError, match="head"):
        chain.snapshot_range(2, 4)


def test_journal_range_repairs_missing_endpoint_indexes():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(journal, 6)
    for sequence in (2, 5):
        key = journal._sequence_key(sequence)
        record = backend.get("journal", key)
        backend.delete(
            "journal",
            key,
            expected_revision=record.revision,
        )
    assert journal.snapshot_range(3, 5) == events[2:5]
    assert journal._sequence_index(2) is not None
    assert journal._sequence_index(5) is not None


def test_receipt_range_repairs_missing_endpoint_indexes():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(chain, 6)
    for sequence in (2, 5):
        key = chain._sequence_key(sequence)
        record = backend.get("receipts", key)
        backend.delete(
            "receipts",
            key,
            expected_revision=record.revision,
        )
    assert chain.snapshot_range(3, 5) == items[2:5]
    assert chain._sequence_index(2) is not None
    assert chain._sequence_index(5) is not None


def test_journal_inspection_reports_multiple_missing_indexes():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_events(journal, 6)
    for sequence in (2, 4, 6):
        key = journal._sequence_key(sequence)
        record = backend.get("journal", key)
        backend.delete(
            "journal",
            key,
            expected_revision=record.revision,
        )
    health = journal.inspect_sequence_indexes()
    assert not health.healthy
    assert health.indexed == 3
    assert health.missing == 3
    assert health.corrupt == 0
    assert health.first_missing_sequence == 2


def test_receipt_inspection_reports_multiple_missing_indexes():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(chain, 6)
    for sequence in (2, 4, 6):
        key = chain._sequence_key(sequence)
        record = backend.get("receipts", key)
        backend.delete(
            "receipts",
            key,
            expected_revision=record.revision,
        )
    health = chain.inspect_sequence_indexes()
    assert not health.healthy
    assert health.indexed == 3
    assert health.missing == 3
    assert health.corrupt == 0
    assert health.first_missing_sequence == 2


def test_journal_repair_rebuilds_all_missing_indexes():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_events(journal, 7)
    for sequence in (1, 3, 7):
        key = journal._sequence_key(sequence)
        record = backend.get("journal", key)
        backend.delete(
            "journal",
            key,
            expected_revision=record.revision,
        )
    repaired = journal.repair_sequence_indexes()
    assert repaired.healthy
    assert repaired.indexed == 7
    assert repaired.missing == 0


def test_receipt_repair_rebuilds_all_missing_indexes():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(chain, 7)
    for sequence in (1, 3, 7):
        key = chain._sequence_key(sequence)
        record = backend.get("receipts", key)
        backend.delete(
            "receipts",
            key,
            expected_revision=record.revision,
        )
    repaired = chain.repair_sequence_indexes()
    assert repaired.healthy
    assert repaired.indexed == 7
    assert repaired.missing == 0


def test_journal_wrong_index_type_is_corruption():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_events(journal, 1)
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="invalid value type",
    ):
        journal.get_by_sequence(1)
    health = journal.inspect_sequence_indexes()
    assert health.corrupt == 1
    assert health.first_corrupt_sequence == 1


def test_receipt_wrong_index_type_is_corruption():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(chain, 1)
    key = chain._sequence_key(1)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="invalid value type",
    ):
        chain.get_by_sequence(1)
    health = chain.inspect_sequence_indexes()
    assert health.corrupt == 1
    assert health.first_corrupt_sequence == 1


def test_journal_conflicting_index_is_corruption():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(journal, 2)
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="wrong event sequence",
    ):
        journal.get_by_sequence(1)
    health = journal.inspect_sequence_indexes()
    assert health.corrupt == 1


def test_receipt_conflicting_index_is_corruption():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(chain, 2)
    key = chain._sequence_key(1)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            items[1].receipt_hash,
        ),
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="wrong node sequence",
    ):
        chain.get_by_sequence(1)
    health = chain.inspect_sequence_indexes()
    assert health.corrupt == 1


def test_journal_repair_refuses_conflicting_index():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(journal, 2)
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="different event",
    ):
        journal.repair_sequence_indexes()


def test_receipt_repair_refuses_conflicting_index():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(chain, 2)
    key = chain._sequence_key(1)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            items[1].receipt_hash,
        ),
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="different node",
    ):
        chain.repair_sequence_indexes()


def test_journal_inspection_honors_bound():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_events(journal, 5)
    with pytest.raises(
        DistributedJournalConflict,
        match="bounded",
    ):
        journal.inspect_sequence_indexes(
            max_items=4,
        )


def test_receipt_inspection_honors_bound():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    append_receipts(chain, 5)
    with pytest.raises(
        DistributedReceiptConflict,
        match="bounded",
    ):
        chain.inspect_sequence_indexes(
            max_items=4,
        )


def test_journal_repair_honors_bound():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_events(journal, 5)
    with pytest.raises(
        DistributedJournalConflict,
        match="bounded",
    ):
        journal.repair_sequence_indexes(
            max_items=4,
        )


def test_receipt_repair_honors_bound():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    append_receipts(chain, 5)
    with pytest.raises(
        DistributedReceiptConflict,
        match="bounded",
    ):
        chain.repair_sequence_indexes(
            max_items=4,
        )


@pytest.mark.parametrize("max_items", [0, -1, True, 1.5])
def test_journal_index_bound_validation(max_items):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="max_items"):
        journal.inspect_sequence_indexes(
            max_items=max_items,
        )
    with pytest.raises(ValueError, match="max_items"):
        journal.repair_sequence_indexes(
            max_items=max_items,
        )


@pytest.mark.parametrize("max_items", [0, -1, True, 1.5])
def test_receipt_index_bound_validation(max_items):
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="max_items"):
        chain.inspect_sequence_indexes(
            max_items=max_items,
        )
    with pytest.raises(ValueError, match="max_items"):
        chain.repair_sequence_indexes(
            max_items=max_items,
        )


def test_journal_health_serialization():
    health = DistributedJournalIndexHealth(
        10,
        10,
        9,
        1,
        0,
        4,
        None,
    )
    data = health.to_dict()
    assert data["head_sequence"] == 10
    assert data["missing"] == 1
    assert data["first_missing_sequence"] == 4
    assert data["healthy"] is False


def test_receipt_health_serialization():
    health = DistributedReceiptIndexHealth(
        10,
        10,
        8,
        1,
        1,
        4,
        7,
    )
    data = health.to_dict()
    assert data["head_sequence"] == 10
    assert data["missing"] == 1
    assert data["corrupt"] == 1
    assert data["first_corrupt_sequence"] == 7
    assert data["healthy"] is False


@pytest.mark.parametrize(
    "cls,kwargs",
    [
        (
            DistributedJournalSequenceIndex,
            {"sequence": 0, "event_hash": fp("a")},
        ),
        (
            DistributedJournalSequenceIndex,
            {"sequence": 1, "event_hash": "bad"},
        ),
        (
            DistributedReceiptSequenceIndex,
            {"sequence": 0, "receipt_hash": fp("a")},
        ),
        (
            DistributedReceiptSequenceIndex,
            {"sequence": 1, "receipt_hash": "bad"},
        ),
    ],
)
def test_sequence_index_validation(cls, kwargs):
    with pytest.raises(ValueError):
        cls(**kwargs)


@pytest.mark.parametrize(
    "cls",
    [
        DistributedJournalIndexHealth,
        DistributedReceiptIndexHealth,
    ],
)
def test_health_rejects_negative_counts(cls):
    with pytest.raises(ValueError):
        cls(
            1,
            1,
            -1,
            0,
            0,
        )


@pytest.mark.parametrize(
    "cls",
    [
        DistributedJournalIndexHealth,
        DistributedReceiptIndexHealth,
    ],
)
def test_health_rejects_invalid_first_sequence(cls):
    with pytest.raises(ValueError):
        cls(
            1,
            1,
            0,
            1,
            0,
            0,
            None,
        )


def test_journal_sequence_index_to_dict():
    item = DistributedJournalSequenceIndex(
        3,
        fp("a"),
    )
    assert item.to_dict() == {
        "sequence": 3,
        "event_hash": fp("a"),
    }


def test_receipt_sequence_index_to_dict():
    item = DistributedReceiptSequenceIndex(
        3,
        fp("a"),
    )
    assert item.to_dict() == {
        "sequence": 3,
        "receipt_hash": fp("a"),
    }


def test_journal_sequence_key_is_fixed_width_and_orderable():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    assert journal._sequence_key(2) < journal._sequence_key(10)
    assert len(journal._sequence_key(2)) == len(
        journal._sequence_key(10)
    )


def test_receipt_sequence_key_is_fixed_width_and_orderable():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    assert chain._sequence_key(2) < chain._sequence_key(10)
    assert len(chain._sequence_key(2)) == len(
        chain._sequence_key(10)
    )


def test_journal_orphan_event_is_not_sequence_indexed():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    committed = append_events(journal, 1)[0]
    orphan = replace(
        committed,
        event_hash=fp("f"),
    )
    backend.put_if_absent(
        "journal",
        journal._event_key(orphan.event_hash),
        orphan,
    )
    assert journal._sequence_index(1).event_hash == committed.event_hash


def test_receipt_orphan_node_is_not_sequence_indexed():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    committed = append_receipts(chain, 1)[0]
    orphan = replace(
        committed,
        receipt_hash=fp("f"),
    )
    backend.put_if_absent(
        "receipts",
        chain._node_key(orphan.receipt_hash),
        orphan,
    )
    assert chain._sequence_index(1).receipt_hash == committed.receipt_hash


def test_journal_range_still_verifies_hash_linkage():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(journal, 4)
    key = journal._event_key(events[2].event_hash)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            events[2],
            summary="tampered",
        ),
    )
    with pytest.raises(
        DistributedJournalCorruption,
    ):
        journal.snapshot_range(2, 4)


def test_receipt_range_still_verifies_hash_linkage():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(chain, 4)
    key = chain._node_key(items[2].receipt_hash)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=replace(
            items[2],
            receipt=replace(
                items[2].receipt,
                stdout_bytes=999,
            ),
        ),
    )
    with pytest.raises(
        DistributedReceiptCorruption,
    ):
        chain.snapshot_range(2, 4)


def test_journal_range_does_not_accept_conflicting_endpoint_index():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_events(journal, 4)
    key = journal._sequence_key(4)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            4,
            events[2].event_hash,
        ),
    )
    with pytest.raises(
        DistributedJournalCorruption,
    ):
        journal.snapshot_range(2, 4)


def test_receipt_range_does_not_accept_conflicting_endpoint_index():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(chain, 4)
    key = chain._sequence_key(4)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            4,
            items[2].receipt_hash,
        ),
    )
    with pytest.raises(
        DistributedReceiptCorruption,
    ):
        chain.snapshot_range(2, 4)
