from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.operation_stream_transport import (
    OperationAccessDenied,
    OperationStreamTransport,
    encode_sse_event,
    encode_sse_heartbeat,
)
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream import ReplayCursor, StreamReplayGapError
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import (
    OperationStoreConflict,
    SQLiteOperationStore,
)


BASE_TIME = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def _operation(
    *,
    tenant_id: str = "tenant-a",
    idempotency_key: str = "idem-1",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=10),
        idempotency_key=idempotency_key,
        trace_id="trace-a",
    )


def _transport(tmp_path: Path):
    operations = SQLiteOperationStore(tmp_path / "operations.sqlite")
    events = SQLiteOperationEventStore(tmp_path / "events.sqlite")
    return OperationStreamTransport(operations, events), operations, events


def test_transport_denies_cross_tenant_status_replay_and_cancel(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation(tenant_id="tenant-a")
    operations.create(operation, now=BASE_TIME)

    try:
        with pytest.raises(OperationAccessDenied, match="not accessible"):
            transport.status(operation.operation_id, tenant_id="tenant-b")
        with pytest.raises(OperationAccessDenied, match="not accessible"):
            transport.replay(operation.operation_id, tenant_id="tenant-b")
        with pytest.raises(OperationAccessDenied, match="not accessible"):
            transport.cancel(operation.operation_id, tenant_id="tenant-b")
    finally:
        operations.close()
        events.close()


def test_transport_dispatches_outbox_and_acknowledges_only_after_stream_acceptance(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    created = operations.create(operation, now=BASE_TIME)
    operations.transition(
        operation.operation_id,
        OperationState.VALIDATED,
        expected_version=created.version,
        now=BASE_TIME + timedelta(seconds=1),
    )

    delivered = transport.dispatch_pending(
        operation.operation_id,
        tenant_id="tenant-a",
    )

    assert [event.type for event in delivered] == [
        "operation.created",
        "operation.validated",
    ]
    assert operations.pending_outbox(operation_id=operation.operation_id) == ()
    assert [event.sequence for event in events.replay(
        ReplayCursor(operation.operation_id)
    )] == [1, 2]

    operations.close()
    events.close()


def test_transport_recovers_when_stream_commit_preceded_outbox_ack(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)
    pending = operations.pending_outbox(operation_id=operation.operation_id)
    assert len(pending) == 1

    item = pending[0]
    first = events.append(
        item.operation_id,
        item.event_type,
        item.payload,
        event_id=item.outbox_id,
        timestamp=item.created_at,
    )
    # Simulate a process crash before acknowledge_outbox.
    assert operations.pending_outbox(operation_id=operation.operation_id)

    delivered = transport.dispatch_pending(
        operation.operation_id,
        tenant_id="tenant-a",
    )

    assert len(delivered) == 1
    assert delivered[0].as_dict() == first.as_dict()
    assert operations.pending_outbox(operation_id=operation.operation_id) == ()
    assert len(events.replay(ReplayCursor(operation.operation_id))) == 1

    operations.close()
    events.close()


def test_shared_sqlite_workers_recover_projection_without_duplicate_events(
    tmp_path: Path,
) -> None:
    operation_path = tmp_path / "shared-operations.sqlite"
    event_path = tmp_path / "shared-events.sqlite"

    operations_a = SQLiteOperationStore(operation_path)
    operations_b = SQLiteOperationStore(operation_path)
    events_a = SQLiteOperationEventStore(event_path)
    events_b = SQLiteOperationEventStore(event_path)
    transport_a = OperationStreamTransport(operations_a, events_a)
    transport_b = OperationStreamTransport(operations_b, events_b)

    operation = _operation()
    created = operations_a.create(operation, now=BASE_TIME)

    # Worker A durably appends the outbox event but crashes before ACK.
    pending = operations_a.pending_outbox(
        operation_id=operation.operation_id,
    )
    assert len(pending) == 1
    item = pending[0]
    appended = events_a.append(
        item.operation_id,
        item.event_type,
        item.payload,
        event_id=item.outbox_id,
        timestamp=item.created_at,
    )

    # Independent worker B replays the same deterministic outbox identity,
    # observes the idempotent append, and completes the ACK.
    recovered = transport_b.dispatch_pending(
        operation.operation_id,
        tenant_id="tenant-a",
    )
    assert len(recovered) == 1
    assert recovered[0].as_dict() == appended.as_dict()
    assert operations_b.pending_outbox(
        operation_id=operation.operation_id,
    ) == ()
    assert len(events_b.replay(ReplayCursor(operation.operation_id))) == 1

    validated = operations_b.transition(
        operation.operation_id,
        OperationState.VALIDATED,
        expected_version=created.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    batch_a = transport_a.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        after_sequence=1,
        consumer_id="worker-a-client",
    )
    assert [event.type for event in batch_a.events] == [
        "operation.validated",
    ]
    assert batch_a.operation.version == validated.version

    cancelled = transport_b.cancel(
        operation.operation_id,
        tenant_id="tenant-a",
    )
    assert cancelled.changed is True
    terminal_a = transport_a.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        after_sequence=2,
        consumer_id="worker-a-client",
    )
    assert [event.type for event in terminal_a.events] == [
        "operation.cancelled",
    ]
    assert terminal_a.terminal is True
    assert terminal_a.stream_latest_sequence == 3
    assert terminal_a.has_more is False

    operations_a.close()
    operations_b.close()
    events_a.close()
    events_b.close()


def test_transport_replay_preserves_explicit_compaction_gap(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    for index, state in enumerate(
        (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
        ),
        start=1,
    ):
        current = operations.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )

    transport.dispatch_pending(operation.operation_id, tenant_id="tenant-a")
    events.compact_through(operation.operation_id, 2)

    with pytest.raises(StreamReplayGapError):
        transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
            after_sequence=1,
        )

    operations.close()
    events.close()


def test_cancel_transitions_authority_and_projects_terminal_event(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)

    first = transport.cancel(operation.operation_id, tenant_id="tenant-a")
    second = transport.cancel(operation.operation_id, tenant_id="tenant-a")

    assert first.changed is True
    assert first.operation.envelope.state is OperationState.CANCELLED
    assert second.changed is False
    assert second.operation.envelope.state is OperationState.CANCELLED

    replay = events.replay(ReplayCursor(operation.operation_id))
    assert [event.type for event in replay] == [
        "operation.created",
        "operation.cancelled",
    ]
    assert replay[-1].terminal is True

    operations.close()
    events.close()


def test_cancel_complete_race_preserves_single_completed_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    for index, state in enumerate(
        (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
            OperationState.ADMITTED,
            OperationState.RUNNING,
        ),
        start=1,
    ):
        current = operations.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )

    original_transition = operations.transition
    raced = False

    def racing_transition(
        operation_id,
        target,
        *,
        expected_version=None,
        now=None,
    ):
        nonlocal raced
        if OperationState(target) is OperationState.CANCELLED and not raced:
            raced = True
            original_transition(
                operation_id,
                OperationState.COMPLETED,
                expected_version=expected_version,
                now=BASE_TIME + timedelta(seconds=10),
            )
            raise OperationStoreConflict(
                "simulated completion won cancellation race"
            )
        return original_transition(
            operation_id,
            target,
            expected_version=expected_version,
            now=now,
        )

    monkeypatch.setattr(operations, "transition", racing_transition)

    result = transport.cancel(
        operation.operation_id,
        tenant_id="tenant-a",
    )

    assert raced is True
    assert result.changed is False
    assert result.operation.envelope.state is OperationState.COMPLETED

    replay = events.replay(ReplayCursor(operation.operation_id))
    terminal = [event for event in replay if event.terminal]
    assert [event.type for event in terminal] == ["operation.completed"]
    assert all(event.type != "operation.cancelled" for event in replay)

    operations.close()
    events.close()


def test_replay_drains_new_outbox_before_reading_cursor(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = operations.transition(
        operation.operation_id,
        OperationState.VALIDATED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )

    batch = transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        after_sequence=0,
    )

    assert [event.type for event in batch.events] == [
        "operation.created",
        "operation.validated",
    ]
    assert batch.latest_sequence == 2
    assert batch.terminal is False

    operations.close()
    events.close()


def test_sse_event_frame_uses_sequence_as_resume_id(tmp_path: Path) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)
    event = transport.dispatch_pending(
        operation.operation_id,
        tenant_id="tenant-a",
    )[0]

    frame = encode_sse_event(event)

    assert frame.startswith("id: 1\nevent: operation.created\ndata: ")
    assert f'"operation_id":"{operation.operation_id}"' in frame
    assert frame.endswith("\n\n")
    assert encode_sse_heartbeat() == ": heartbeat\n\n"

    operations.close()
    events.close()


def test_transport_registers_and_acknowledges_tenant_consumer(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)

    batch = transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-a",
        after_sequence=0,
    )
    checkpoint = transport.acknowledge(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-a",
        sequence=batch.latest_sequence,
    )

    assert checkpoint.acknowledged_through == 1
    assert events.safe_compaction_sequence(operation.operation_id) == 1

    operations.close()
    events.close()


def test_transport_acknowledgement_is_tenant_bound(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation(tenant_id="tenant-a")
    operations.create(operation, now=BASE_TIME)
    transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-a",
    )

    with pytest.raises(OperationAccessDenied):
        transport.acknowledge(
            operation.operation_id,
            tenant_id="tenant-b",
            consumer_id="client-a",
            sequence=1,
        )

    operations.close()
    events.close()


def test_resync_snapshot_returns_compaction_floor_and_latest_cursor(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    for index, state in enumerate(
        (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
        ),
        start=1,
    ):
        current = operations.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )

    transport.dispatch_pending(operation.operation_id, tenant_id="tenant-a")
    events.compact_through(operation.operation_id, 2)

    snapshot = transport.resync_snapshot(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-recover",
    )

    assert snapshot.compacted_through == 2
    assert snapshot.resume_after_sequence == 2
    assert snapshot.latest_sequence == 3
    assert snapshot.operation.envelope.state is OperationState.AUTHORIZED
    assert snapshot.active_consumer_count == 1

    replay = transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        after_sequence=snapshot.resume_after_sequence,
        consumer_id="client-recover",
    )
    assert [event.sequence for event in replay.events] == [3]

    operations.close()
    events.close()


def test_acknowledge_and_compact_waits_for_slowest_active_consumer(
    tmp_path: Path,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    for index, state in enumerate(
        (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
        ),
        start=1,
    ):
        current = operations.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )

    first = transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-a",
        after_sequence=0,
    )
    second = transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-b",
        after_sequence=0,
    )
    assert first.latest_sequence == second.latest_sequence == 3

    fast = transport.acknowledge_and_compact(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-a",
        sequence=3,
    )
    assert fast.compacted_through == 0
    assert fast.compacted_events == 0
    assert fast.active_consumer_count == 2

    slow = transport.acknowledge_and_compact(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="client-b",
        sequence=2,
    )
    assert slow.compacted_through == 2
    assert slow.compacted_events == 2
    assert slow.latest_sequence == 3

    with pytest.raises(StreamReplayGapError):
        transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
            after_sequence=1,
        )

    operations.close()
    events.close()



def test_projection_lease_serializes_workers_and_allows_clean_takeover(tmp_path: Path) -> None:
    operation_path = tmp_path / "shared-operations.sqlite"
    event_path = tmp_path / "shared-events.sqlite"
    operations_a = SQLiteOperationStore(operation_path)
    operations_b = SQLiteOperationStore(operation_path)
    events_a = SQLiteOperationEventStore(event_path)
    events_b = SQLiteOperationEventStore(event_path)
    transport_b = OperationStreamTransport(operations_b, events_b, worker_id="worker-b", projection_lease_seconds=60)
    operation = _operation()
    operations_a.create(operation, now=BASE_TIME)
    try:
        held = events_a.acquire_worker_lease(operation.operation_id, "worker-a", lease_seconds=60)
        assert held is not None
        assert transport_b.dispatch_pending(operation.operation_id, tenant_id="tenant-a") == ()
        assert len(operations_b.pending_outbox(operation_id=operation.operation_id)) == 1
        assert events_b.head(operation.operation_id)["latest_sequence"] == 0
        assert events_a.release_worker_lease(operation.operation_id, "worker-a", held.generation) is True
        delivered = transport_b.dispatch_pending(operation.operation_id, tenant_id="tenant-a")
        assert [event.type for event in delivered] == ["operation.created"]
        assert operations_b.pending_outbox(operation_id=operation.operation_id) == ()
        assert [event.sequence for event in events_b.replay(ReplayCursor(operation.operation_id))] == [1]
    finally:
        operations_a.close(); operations_b.close(); events_a.close(); events_b.close()
