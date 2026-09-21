from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.frontier.operation_stream import (
    ReplayCursor,
    StreamBackpressureError,
    StreamDuplicateConflictError,
    StreamEvent,
    StreamReplayGapError,
    StreamTerminalError,
)
from skeleton.frontier.operation_stream_store import (
    SQLiteOperationEventStore,
    StreamStoreCorruptionError,
)


def test_sqlite_stream_persists_ordered_replay_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    operation_id = str(uuid4())

    with SQLiteOperationEventStore(path) as store:
        first = store.append(operation_id, "operation.started", {"stage": "route"})
        second = store.append(operation_id, "operation.progress", {"stage": "provider"})
        assert (first.sequence, second.sequence) == (1, 2)

    with SQLiteOperationEventStore(path) as store:
        replay = store.replay(ReplayCursor(operation_id, after_sequence=0))
        assert [event.sequence for event in replay] == [1, 2]
        assert [event.type for event in replay] == [
            "operation.started",
            "operation.progress",
        ]


def test_sqlite_stream_terminal_is_durable(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    operation_id = str(uuid4())

    with SQLiteOperationEventStore(path) as store:
        terminal = store.append(operation_id, "operation.completed", {"ok": True})
        assert terminal.terminal is True
        assert store.head(operation_id)["terminal"] is True

    with SQLiteOperationEventStore(path) as store:
        with pytest.raises(StreamTerminalError):
            store.append(operation_id, "operation.progress", {"late": True})


def test_sqlite_stream_compaction_creates_explicit_replay_gap(tmp_path: Path) -> None:
    operation_id = str(uuid4())
    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        store.append(operation_id, "operation.started", {})
        store.append(operation_id, "operation.progress", {"n": 1})
        store.append(operation_id, "operation.progress", {"n": 2})

        assert store.compact_through(operation_id, 2) == 2
        assert store.head(operation_id)["compacted_through"] == 2

        with pytest.raises(StreamReplayGapError):
            store.replay(ReplayCursor(operation_id, after_sequence=1))

        replay = store.replay(ReplayCursor(operation_id, after_sequence=2))
        assert [event.sequence for event in replay] == [3]


def test_sqlite_stream_capacity_backpressures_without_drop(tmp_path: Path) -> None:
    operation_id = str(uuid4())
    with SQLiteOperationEventStore(
        tmp_path / "events.sqlite",
        capacity_per_operation=2,
    ) as store:
        store.append(operation_id, "operation.started", {})
        store.append(operation_id, "operation.progress", {"n": 1})
        with pytest.raises(StreamBackpressureError):
            store.append(operation_id, "operation.progress", {"n": 2})

        assert [event.sequence for event in store.replay(ReplayCursor(operation_id))] == [1, 2]


def test_sqlite_stream_duplicate_identity_is_idempotent_only_when_identical(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    event = StreamEvent(
        operation_id=operation_id,
        event_id=event_id,
        sequence=1,
        type="operation.started",
        timestamp=timestamp,
        payload={"x": 1},
    )

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        assert store.append_event(event).as_dict() == event.as_dict()
        assert store.append_event(event).as_dict() == event.as_dict()

        conflict = StreamEvent(
            operation_id=operation_id,
            event_id=event_id,
            sequence=2,
            type="operation.progress",
            timestamp=timestamp,
            payload={"x": 2},
        )
        with pytest.raises(StreamDuplicateConflictError):
            store.append_event(conflict)


def test_sqlite_stream_detects_persisted_payload_corruption(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    operation_id = str(uuid4())
    with SQLiteOperationEventStore(path) as store:
        store.append(operation_id, "operation.started", {"ok": True})
        store._connection.execute(
            """
            UPDATE operation_stream_event
            SET payload_json = ?
            WHERE namespace = ? AND operation_id = ? AND sequence = 1
            """,
            ('{"x": NaN}', store.namespace, operation_id),
        )

        with pytest.raises(StreamStoreCorruptionError):
            store.replay(ReplayCursor(operation_id))


def test_sqlite_stream_explicit_event_id_append_is_retry_idempotent(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        first = store.append(
            operation_id,
            "operation.validated",
            {"state": "validated", "version": 2},
            event_id=event_id,
            timestamp=timestamp,
        )
        retry = store.append(
            operation_id,
            "operation.validated",
            {"state": "validated", "version": 2},
            event_id=event_id,
            timestamp=timestamp,
        )

        assert retry.as_dict() == first.as_dict()
        assert store.head(operation_id)["latest_sequence"] == 1
        assert len(store.replay(ReplayCursor(operation_id))) == 1


def test_sqlite_stream_explicit_event_id_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        store.append(
            operation_id,
            "operation.progress",
            {"step": 1},
            event_id=event_id,
            timestamp=timestamp,
        )

        with pytest.raises(StreamDuplicateConflictError):
            store.append(
                operation_id,
                "operation.progress",
                {"step": 2},
                event_id=event_id,
                timestamp=timestamp,
            )
