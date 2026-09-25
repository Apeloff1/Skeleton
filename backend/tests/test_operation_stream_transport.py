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
from skeleton.frontier.operation_stream import (
    ReplayCursor,
    StreamBackpressureError,
    StreamReplayGapError,
)
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

def test_slow_client_forces_backpressure_until_lease_expiry_frees_capacity(
    tmp_path: Path,
) -> None:
    operations = SQLiteOperationStore(tmp_path / "slow-operations.sqlite")
    events = SQLiteOperationEventStore(
        tmp_path / "slow-events.sqlite",
        capacity_per_operation=3,
    )
    transport = OperationStreamTransport(operations, events)
    operation = _operation(idempotency_key="slow-client")
    current = operations.create(operation, now=BASE_TIME)
    current = operations.transition(
        operation.operation_id,
        OperationState.VALIDATED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    current = operations.transition(
        operation.operation_id,
        OperationState.AUTHORIZED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=2),
    )
    transport.dispatch_pending(operation.operation_id, tenant_id="tenant-a")
    assert events.head(operation.operation_id)["latest_sequence"] == 3

    events.register_consumer(
        operation.operation_id,
        "fast-client",
        lease_seconds=300,
        now=BASE_TIME + timedelta(seconds=3),
    )
    events.register_consumer(
        operation.operation_id,
        "slow-client",
        lease_seconds=1,
        now=BASE_TIME + timedelta(seconds=3),
    )
    events.acknowledge_consumer(
        operation.operation_id,
        "fast-client",
        3,
        lease_seconds=300,
        now=BASE_TIME + timedelta(seconds=3),
    )
    assert (
        events.compact_acknowledged(
            operation.operation_id,
            now=BASE_TIME + timedelta(seconds=3),
        )
        == 0
    )

    current = operations.transition(
        operation.operation_id,
        OperationState.ADMITTED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=4),
    )
    with pytest.raises(StreamBackpressureError, match="capacity"):
        transport.dispatch_pending(
            operation.operation_id,
            tenant_id="tenant-a",
        )
    assert len(
        operations.pending_outbox(operation_id=operation.operation_id)
    ) == 1

    compacted = events.compact_acknowledged(
        operation.operation_id,
        now=BASE_TIME + timedelta(seconds=5),
    )
    assert compacted == 3
    assert events.head(operation.operation_id)["compacted_through"] == 3

    delivered = transport.dispatch_pending(
        operation.operation_id,
        tenant_id="tenant-a",
    )
    assert [event.sequence for event in delivered] == [4]
    assert [event.type for event in delivered] == ["operation.admitted"]
    assert operations.pending_outbox(operation_id=operation.operation_id) == ()

    operations.close()
    events.close()


def test_completion_wins_cancel_race_without_cancelled_terminal_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    transport, operations, events = _transport(tmp_path)
    operation = _operation(idempotency_key="cancel-complete-race")
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

    def racing_transition(operation_id, target, **kwargs):
        if OperationState(target) is OperationState.CANCELLED:
            latest = operations.get(operation_id)
            original_transition(
                operation_id,
                OperationState.COMPLETED,
                expected_version=latest.version,
                now=BASE_TIME + timedelta(seconds=20),
            )
            raise OperationStoreConflict("simulated cancel/complete race")
        return original_transition(operation_id, target, **kwargs)

    monkeypatch.setattr(operations, "transition", racing_transition)

    result = transport.cancel(
        operation.operation_id,
        tenant_id="tenant-a",
    )

    assert result.changed is False
    assert result.operation.envelope.state is OperationState.COMPLETED
    replay = events.replay(ReplayCursor(operation.operation_id))
    assert replay[-1].type == "operation.completed"
    assert replay[-1].terminal is True
    assert all(event.type != "operation.cancelled" for event in replay)

    second = transport.cancel(
        operation.operation_id,
        tenant_id="tenant-a",
    )
    assert second.changed is False
    assert second.operation.envelope.state is OperationState.COMPLETED

    operations.close()
    events.close()

