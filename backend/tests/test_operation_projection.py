from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.operation_projection import (
    OperationProjectionError,
    ProjectionConflictError,
    ProjectionResyncRequired,
    apply_projection_event,
    apply_projection_events,
    resync_projection,
    start_projection,
    verify_projection_authority,
)
from core.operation_stream_transport import OperationStreamTransport
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream import StreamEvent
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import (
    SQLiteOperationStore,
    StoredOperation,
)


BASE_TIME = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _operation(
    *,
    tenant_id: str = "tenant-a",
    idempotency_key: str = "projection-test",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=10),
        idempotency_key=idempotency_key,
        trace_id="trace-projection",
    )


def _runtime(tmp_path: Path, *, worker_id: str = "worker-a"):
    operations = SQLiteOperationStore(tmp_path / "operations.sqlite")
    events = SQLiteOperationEventStore(tmp_path / "events.sqlite")
    transport = OperationStreamTransport(
        operations,
        events,
        worker_id=worker_id,
    )
    return transport, operations, events


def _advance(
    operations: SQLiteOperationStore,
    current: StoredOperation,
    *states: OperationState,
) -> StoredOperation:
    for index, state in enumerate(states, start=1):
        current = operations.transition(
            current.envelope.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )
    return current


def test_full_replay_converges_to_durable_authority(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
        OperationState.ADMITTED,
        OperationState.RUNNING,
        OperationState.COMPLETED,
    )
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
            after_sequence=0,
            limit=64,
        )
        projection = apply_projection_events(
            start_projection(current),
            batch.events,
        )
        decision = verify_projection_authority(
            projection,
            current,
        )

        assert decision.accepted is True
        assert decision.reasons == ()
        assert projection.cursor_sequence == current.version
        assert projection.operation_version == current.version
        assert projection.state is OperationState.COMPLETED
        assert projection.terminal is True
        evidence = decision.accepted_evidence_ref()
        assert evidence.category == "streaming_projection_authority"
        assert evidence.digest == decision.decision_digest
    finally:
        operations.close()
        events.close()


def test_exact_duplicate_delivery_is_idempotent(tmp_path: Path) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        projection = start_projection(current)
        applied = apply_projection_event(
            projection,
            batch.events[0],
        )
        duplicate = apply_projection_event(
            applied,
            batch.events[0],
        )

        assert duplicate == applied
        assert duplicate.cursor_sequence == 1
        assert duplicate.operation_version == 1
    finally:
        operations.close()
        events.close()


def test_conflicting_duplicate_sequence_fails_closed(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        event = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        ).events[0]
        projection = apply_projection_event(
            start_projection(current),
            event,
        )
        conflicting = StreamEvent(
            operation_id=event.operation_id,
            event_id=str(uuid4()),
            sequence=event.sequence,
            type=event.type,
            timestamp=event.timestamp,
            payload=dict(event.payload),
        )

        with pytest.raises(
            ProjectionConflictError,
            match="duplicate sequence conflicts",
        ):
            apply_projection_event(projection, conflicting)
    finally:
        operations.close()
        events.close()


def test_out_of_order_gap_requires_resync(tmp_path: Path) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
    )
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        projection = apply_projection_event(
            start_projection(current),
            batch.events[0],
        )

        with pytest.raises(
            ProjectionResyncRequired,
            match="stream gap",
        ):
            apply_projection_event(projection, batch.events[2])
    finally:
        operations.close()
        events.close()


def test_illegal_state_transition_is_never_projected(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        created = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        ).events[0]
        projection = apply_projection_event(
            start_projection(current),
            created,
        )
        illegal = StreamEvent(
            operation_id=operation.operation_id,
            event_id=str(uuid4()),
            sequence=2,
            type="operation.running",
            timestamp=BASE_TIME + timedelta(seconds=1),
            payload={
                "state": "running",
                "version": 2,
                "trace_id": operation.trace_id,
            },
        )

        with pytest.raises(
            ProjectionConflictError,
            match="canonical operation transition",
        ):
            apply_projection_event(projection, illegal)
    finally:
        operations.close()
        events.close()


def test_operation_version_drift_requires_resync(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        created = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        ).events[0]
        projection = apply_projection_event(
            start_projection(current),
            created,
        )
        drift = StreamEvent(
            operation_id=operation.operation_id,
            event_id=str(uuid4()),
            sequence=2,
            type="operation.validated",
            timestamp=BASE_TIME + timedelta(seconds=1),
            payload={
                "state": "validated",
                "version": 9,
                "trace_id": operation.trace_id,
            },
        )

        with pytest.raises(
            ProjectionResyncRequired,
            match="operation version",
        ):
            apply_projection_event(projection, drift)
    finally:
        operations.close()
        events.close()


def test_trace_identity_drift_fails_closed(tmp_path: Path) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
    )
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        projection = apply_projection_event(
            start_projection(current),
            batch.events[0],
        )
        event = batch.events[1]
        drift = StreamEvent(
            operation_id=event.operation_id,
            event_id=event.event_id,
            sequence=event.sequence,
            type=event.type,
            timestamp=event.timestamp,
            payload={
                **dict(event.payload),
                "trace_id": "other-trace",
            },
        )

        with pytest.raises(
            ProjectionConflictError,
            match="trace identity mismatch",
        ):
            apply_projection_event(projection, drift)
    finally:
        operations.close()
        events.close()


def test_resync_binds_exact_stream_head_to_durable_version(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
    )
    try:
        transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        head = events.head(operation.operation_id)
        assert head["latest_sequence"] == current.version

        projection = resync_projection(
            current,
            stream_latest_sequence=int(head["latest_sequence"]),
        )
        decision = verify_projection_authority(
            projection,
            current,
        )
        assert decision.accepted is True

        with pytest.raises(
            ProjectionResyncRequired,
            match="stream head sequence",
        ):
            resync_projection(
                current,
                stream_latest_sequence=current.version - 1,
            )
    finally:
        operations.close()
        events.close()


def test_unknown_old_duplicate_after_resync_requires_resync(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
    )
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        projection = resync_projection(
            current,
            stream_latest_sequence=current.version,
        )

        with pytest.raises(
            ProjectionResyncRequired,
            match="predates exact receipt window",
        ):
            apply_projection_event(projection, batch.events[0])
    finally:
        operations.close()
        events.close()


def test_reconnect_can_switch_workers_and_converge(
    tmp_path: Path,
) -> None:
    operation_path = tmp_path / "shared-operations.sqlite"
    event_path = tmp_path / "shared-events.sqlite"
    operations_a = SQLiteOperationStore(operation_path)
    operations_b = SQLiteOperationStore(operation_path)
    events_a = SQLiteOperationEventStore(event_path)
    events_b = SQLiteOperationEventStore(event_path)
    transport_a = OperationStreamTransport(
        operations_a,
        events_a,
        worker_id="worker-a",
    )
    transport_b = OperationStreamTransport(
        operations_b,
        events_b,
        worker_id="worker-b",
    )
    operation = _operation(idempotency_key="worker-reconnect")
    current = operations_a.create(operation, now=BASE_TIME)
    current = operations_a.transition(
        operation.operation_id,
        OperationState.VALIDATED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    try:
        first = transport_a.replay(
            operation.operation_id,
            tenant_id="tenant-a",
            after_sequence=0,
            limit=1,
        )
        projection = apply_projection_events(
            start_projection(current),
            first.events,
        )
        assert projection.cursor_sequence == 1

        current = operations_b.transition(
            operation.operation_id,
            OperationState.AUTHORIZED,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=2),
        )
        resumed = transport_b.replay(
            operation.operation_id,
            tenant_id="tenant-a",
            after_sequence=projection.cursor_sequence,
            limit=64,
        )
        projection = apply_projection_events(
            projection,
            resumed.events,
        )
        decision = verify_projection_authority(
            projection,
            operations_b.get(operation.operation_id),
        )

        assert [item.sequence for item in projection.recent_events] == [1, 2, 3]
        assert projection.state is OperationState.AUTHORIZED
        assert decision.accepted is True
    finally:
        operations_a.close()
        operations_b.close()
        events_a.close()
        events_b.close()


def test_authority_tenant_or_identity_drift_is_rejected(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        projection = apply_projection_events(
            start_projection(current),
            batch.events,
        )
        mismatched = StoredOperation(
            envelope=replace(
                current.envelope,
                tenant_id="tenant-b",
            ),
            version=current.version,
            updated_at=current.updated_at,
        )
        decision = verify_projection_authority(
            projection,
            mismatched,
        )

        assert decision.accepted is False
        assert "tenant-id-mismatch" in decision.reasons
        assert "operation-identity-digest-mismatch" in decision.reasons
        with pytest.raises(
            OperationProjectionError,
            match="cannot become promotion",
        ):
            decision.accepted_evidence_ref()
    finally:
        operations.close()
        events.close()


def test_terminal_projection_cannot_advance_to_another_state(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
        OperationState.ADMITTED,
        OperationState.RUNNING,
        OperationState.COMPLETED,
    )
    try:
        batch = transport.replay(
            operation.operation_id,
            tenant_id="tenant-a",
        )
        projection = apply_projection_events(
            start_projection(current),
            batch.events,
        )
        after_terminal = StreamEvent(
            operation_id=operation.operation_id,
            event_id=str(uuid4()),
            sequence=projection.cursor_sequence + 1,
            type="operation.failed",
            timestamp=BASE_TIME + timedelta(seconds=10),
            payload={
                "state": "failed",
                "version": projection.operation_version + 1,
                "trace_id": operation.trace_id,
            },
        )

        with pytest.raises(
            ProjectionConflictError,
            match="canonical operation transition",
        ):
            apply_projection_event(
                projection,
                after_terminal,
            )
    finally:
        operations.close()
        events.close()
