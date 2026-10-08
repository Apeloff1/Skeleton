"""VOL-039 durable SQLite event stream integrity and verified replay.

Checks original operation/event contracts and deliberate SQLite fault injection.
The auditor is bounded and read-only for existing event/consumer rows; this
does not claim cryptographic evidence or remote multi-writer transactions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.frontier.runtime.event_architecture import EventRetentionPolicy
from skeleton.frontier.runtime.operation_stream import ReplayCursor, StreamReplayGapError
from skeleton.frontier.runtime.operation_stream_store import (
    SQLiteOperationEventStore, StreamStoreCorruptionError,
)


def seeded(store: SQLiteOperationEventStore, *, length: int = 5, terminal: bool = False) -> str:
    operation_id = str(uuid4())
    for sequence in range(1, length + 1):
        event_type = "operation.completed" if terminal and sequence == length else "operation.progress"
        store.append(operation_id, event_type, {"counter": sequence})
    return operation_id


def test_integrity_audit_happy_path_and_paged_verified_replay(tmp_path: Path):
    with SQLiteOperationEventStore(tmp_path / "durable.sqlite") as store:
        operation_id = seeded(store, length=7)
        report = store.audit_operation(operation_id, batch_size=2)
        assert report.operation_id == operation_id
        assert report.retained_events == 7
        assert report.latest_sequence == 7
        assert report.compacted_through == 0
        assert report.terminal is False
        assert report.terminal_sequence is None
        assert [x.sequence for x in store.replay_verified(
            ReplayCursor(operation_id), limit=3,
        )] == [1, 2, 3]
        assert [x.sequence for x in store.replay_verified(
            ReplayCursor(operation_id, after_sequence=3), limit=3,
        )] == [4, 5, 6]
    with SQLiteOperationEventStore(tmp_path / "durable.sqlite") as reopened:
        assert reopened.audit_operation(operation_id).latest_sequence == 7
        assert reopened.audit_operation(operation_id).retained_events == 7


def test_integrity_audit_detects_midstream_sequence_hole():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=4)
        store._connection.execute(
            "DELETE FROM operation_stream_event WHERE operation_id=? AND sequence=2",
            (operation_id,),
        )
        with pytest.raises(StreamStoreCorruptionError, match="sequence gap"):
            store.audit_operation(operation_id, batch_size=2)
        with pytest.raises(StreamStoreCorruptionError, match="sequence gap"):
            store.replay_verified(ReplayCursor(operation_id))


def test_integrity_audit_detects_missing_first_uncompacted_event():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3)
        store._connection.execute(
            "DELETE FROM operation_stream_event WHERE operation_id=? AND sequence=1",
            (operation_id,),
        )
        with pytest.raises(StreamStoreCorruptionError, match="sequence gap"):
            store.audit_operation(operation_id)


def test_integrity_audit_detects_corrupt_json_payload():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3)
        store._connection.execute(
            "UPDATE operation_stream_event SET payload_json=? "
            "WHERE operation_id=? AND sequence=2",
            ("{bad json", operation_id),
        )
        with pytest.raises(StreamStoreCorruptionError, match="payload"):
            store.audit_operation(operation_id)


def test_integrity_audit_detects_unexpected_terminal_event_without_head():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3)
        store._connection.execute(
            "UPDATE operation_stream_event SET event_type='operation.completed' "
            "WHERE operation_id=? AND sequence=3",
            (operation_id,),
        )
        with pytest.raises(StreamStoreCorruptionError, match="head remains nonterminal"):
            store.audit_operation(operation_id)


def test_integrity_audit_detects_terminal_head_missing_marker():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3)
        store._connection.execute(
            "UPDATE operation_stream_head SET terminal=1 WHERE operation_id=?",
            (operation_id,),
        )
        with pytest.raises(StreamStoreCorruptionError, match="terminal head"):
            store.audit_operation(operation_id)


def test_integrity_audit_detects_events_after_terminal():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3, terminal=True)
        store._connection.execute(
            "UPDATE operation_stream_event SET event_type='operation.completed' "
            "WHERE operation_id=? AND sequence=2",
            (operation_id,),
        )
        with pytest.raises(StreamStoreCorruptionError, match="follows a terminal"):
            store.audit_operation(operation_id)


def test_integrity_audit_detects_impossible_consumer_ack():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3)
        base = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
        store.register_consumer(operation_id, "consumer", now=base)
        store._connection.execute(
            "UPDATE operation_stream_consumer SET acknowledged_through=99 "
            "WHERE operation_id=? AND consumer_id='consumer'",
            (operation_id,),
        )
        with pytest.raises(StreamStoreCorruptionError, match="acknowledgement"):
            store.audit_operation(operation_id)


def test_integrity_audit_recovers_after_acknowledged_compaction():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=5)
        base = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
        store.register_consumer(operation_id, "reader", now=base)
        store.acknowledge_consumer(
            operation_id, "reader", 5, now=base + timedelta(seconds=1)
        )
        count = store.compact_with_retention(
            operation_id, EventRetentionPolicy(minimum_retained_events=2),
            now=base + timedelta(seconds=2),
        )
        assert count == 3
        report = store.audit_operation(operation_id, batch_size=1)
        assert report.compacted_through == 3
        assert report.retained_events == 2
        assert report.latest_sequence == 5
        assert report.consumer_count == 1
        assert [e.sequence for e in store.replay_verified(
            ReplayCursor(operation_id, after_sequence=3),
        )] == [4, 5]
        with pytest.raises(StreamReplayGapError):
            store.replay_verified(ReplayCursor(operation_id, after_sequence=2))


def test_integrity_audit_fully_compacted_terminal_is_valid():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=3, terminal=True)
        base = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
        store.register_consumer(operation_id, "reader", now=base)
        store.acknowledge_consumer(operation_id, "reader", 3, now=base)
        deleted = store.compact_with_retention(
            operation_id,
            EventRetentionPolicy(
                minimum_retained_events=0,
                terminal_minimum_retained_events=0,
            ),
            now=base,
        )
        assert deleted == 3
        report = store.audit_operation(operation_id)
        assert report.terminal is True
        assert report.terminal_sequence is None
        assert report.compacted_through == 3
        assert report.latest_sequence == 3
        assert report.retained_events == 0


def test_integrity_audit_budget_rejects_large_recovery_scan():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=5)
        with pytest.raises(StreamStoreCorruptionError, match="scan event budget"):
            store.audit_operation(operation_id, max_events=4, batch_size=2)
        assert store.audit_operation(operation_id, max_events=5, batch_size=2).retained_events == 5


def test_integrity_audit_rejects_noninteger_or_excessive_budgets():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=1)
        for bad in (True, 0, -1, "10", 1.2, 1_000_001):
            with pytest.raises(ValueError):
                store.audit_operation(operation_id, max_events=bad)
        for bad in (True, 0, -1, "3", 4097):
            with pytest.raises(ValueError):
                store.audit_operation(operation_id, batch_size=bad)


def test_verified_replay_rejects_oversized_read_and_wrong_cursor():
    with SQLiteOperationEventStore() as store:
        operation_id = seeded(store, length=1)
        for bad in (True, 0, -1, 4097, "10"):
            with pytest.raises(ValueError):
                store.replay_verified(ReplayCursor(operation_id), limit=bad)
        with pytest.raises(Exception, match="ReplayCursor"):
            store.replay_verified(object())


def test_integrity_audit_empty_stream_is_valid_and_bounded():
    operation_id = str(uuid4())
    with SQLiteOperationEventStore() as store:
        report = store.audit_operation(operation_id)
        assert report.retained_events == 0
        assert report.latest_sequence == 0
        assert report.compacted_through == 0
        assert store.replay_verified(ReplayCursor(operation_id)) == ()
