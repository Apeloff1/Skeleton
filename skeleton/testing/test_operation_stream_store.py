from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.frontier.operation_stream import (
    ReplayCursor,
    StreamContractError,
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


def test_consumer_acknowledgements_gate_safe_compaction(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    base = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        for index in range(1, 5):
            store.append(
                operation_id,
                "operation.progress",
                {"step": index},
                timestamp=base + timedelta(seconds=index),
            )

        store.register_consumer(
            operation_id,
            "client-a",
            lease_seconds=300,
            now=base,
        )
        store.register_consumer(
            operation_id,
            "client-b",
            lease_seconds=300,
            now=base,
        )
        store.acknowledge_consumer(
            operation_id,
            "client-a",
            3,
            lease_seconds=300,
            now=base + timedelta(seconds=1),
        )
        store.acknowledge_consumer(
            operation_id,
            "client-b",
            2,
            lease_seconds=300,
            now=base + timedelta(seconds=1),
        )

        assert store.safe_compaction_sequence(
            operation_id,
            now=base + timedelta(seconds=2),
        ) == 2
        assert store.compact_acknowledged(
            operation_id,
            now=base + timedelta(seconds=2),
        ) == 2
        assert store.head(operation_id)["compacted_through"] == 2


def test_expired_consumer_stops_blocking_active_consumer_watermark(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    base = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        for index in range(1, 6):
            store.append(
                operation_id,
                "operation.progress",
                {"step": index},
                timestamp=base + timedelta(seconds=index),
            )

        store.register_consumer(
            operation_id,
            "slow-client",
            lease_seconds=1,
            now=base,
        )
        store.acknowledge_consumer(
            operation_id,
            "slow-client",
            1,
            lease_seconds=1,
            now=base,
        )
        store.register_consumer(
            operation_id,
            "active-client",
            lease_seconds=300,
            now=base,
        )
        store.acknowledge_consumer(
            operation_id,
            "active-client",
            4,
            lease_seconds=300,
            now=base,
        )

        assert store.safe_compaction_sequence(
            operation_id,
            now=base + timedelta(seconds=2),
        ) == 4
        consumers = store.active_consumers(
            operation_id,
            now=base + timedelta(seconds=2),
        )
        assert [item.consumer_id for item in consumers] == ["active-client"]


def test_consumer_ack_is_monotonic_and_cannot_exceed_stream_head(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    base = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        for index in range(1, 4):
            store.append(
                operation_id,
                "operation.progress",
                {"step": index},
                timestamp=base + timedelta(seconds=index),
            )
        store.register_consumer(operation_id, "client-a", now=base)

        first = store.acknowledge_consumer(
            operation_id,
            "client-a",
            2,
            now=base + timedelta(seconds=1),
        )
        regressed = store.acknowledge_consumer(
            operation_id,
            "client-a",
            1,
            now=base + timedelta(seconds=2),
        )

        assert first.acknowledged_through == 2
        assert regressed.acknowledged_through == 2

        with pytest.raises(StreamContractError, match="beyond latest"):
            store.acknowledge_consumer(
                operation_id,
                "client-a",
                4,
                now=base + timedelta(seconds=3),
            )


def test_consumer_must_register_before_acknowledging(tmp_path: Path) -> None:
    operation_id = str(uuid4())

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        store.append(operation_id, "operation.created", {"state": "created"})

        with pytest.raises(StreamContractError, match="register"):
            store.acknowledge_consumer(operation_id, "unknown-client", 1)


def test_no_active_consumers_never_advances_compaction_implicitly(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        store.append(operation_id, "operation.created", {"state": "created"})
        assert store.safe_compaction_sequence(operation_id) == 0
        assert store.compact_acknowledged(operation_id) == 0
        assert store.head(operation_id)["compacted_through"] == 0



def test_worker_projection_lease_is_fenced_and_takeover_waits_for_expiry(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    operation_id = str(uuid4())
    base = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
    store_a = SQLiteOperationEventStore(path)
    store_b = SQLiteOperationEventStore(path)
    try:
        first = store_a.acquire_worker_lease(operation_id, "worker-a", lease_seconds=10, now=base)
        assert first is not None and first.generation == 1
        assert store_b.acquire_worker_lease(operation_id, "worker-b", lease_seconds=10, now=base + timedelta(seconds=5)) is None
        renewed = store_a.renew_worker_lease(operation_id, "worker-a", first.generation, lease_seconds=10, now=base + timedelta(seconds=5))
        assert renewed is not None and renewed.generation == first.generation
        takeover = store_b.acquire_worker_lease(operation_id, "worker-b", lease_seconds=10, now=base + timedelta(seconds=16))
        assert takeover is not None and takeover.generation == first.generation + 1
        assert store_a.release_worker_lease(operation_id, "worker-a", first.generation) is False
        active = store_b.active_worker_lease(operation_id, now=base + timedelta(seconds=16))
        assert active is not None and active.worker_id == "worker-b" and active.generation == takeover.generation
        assert store_b.release_worker_lease(operation_id, "worker-b", takeover.generation) is True
    finally:
        store_a.close()
        store_b.close()


def test_same_worker_cannot_reenter_live_lease_and_generation_advances_after_expiry(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    base = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)
    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        first = store.acquire_worker_lease(
            operation_id,
            "worker-a",
            lease_seconds=30,
            now=base,
        )
        assert first is not None
        assert store.acquire_worker_lease(
            operation_id,
            "worker-a",
            lease_seconds=30,
            now=base + timedelta(seconds=1),
        ) is None

        second = store.acquire_worker_lease(
            operation_id,
            "worker-a",
            lease_seconds=30,
            now=base + timedelta(seconds=31),
        )
        assert second is not None
        assert second.generation == first.generation + 1
        assert store.release_worker_lease(
            operation_id,
            "worker-a",
            first.generation,
        ) is False
        assert store.release_worker_lease(
            operation_id,
            "worker-a",
            second.generation,
        ) is True
