from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.operation_projection import (
    OperationProjection,
    ProjectionAuthorityError,
    ProjectionSource,
    apply_resync_snapshot,
    apply_stream_batch,
    bootstrap_projection,
)
from core.operation_stream_transport import (
    OperationResyncSnapshot,
    OperationStreamBatch,
    OperationStreamTransport,
)
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream import StreamEvent
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import SQLiteOperationStore


BASE_TIME = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)


def _operation(
    tenant_id: str = "tenant-a",
    *,
    operation_id: str | None = None,
    trace_id: str = "trace-projection",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=operation_id or str(uuid4()),
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=20),
        idempotency_key="idem-projection",
        trace_id=trace_id,
    )


def _runtime(tmp_path: Path):
    operations = SQLiteOperationStore(tmp_path / "operations.sqlite")
    events = SQLiteOperationEventStore(tmp_path / "events.sqlite")
    transport = OperationStreamTransport(
        operations,
        events,
        worker_id="projection-test-worker",
    )
    return transport, operations, events


def _authorized_runtime(tmp_path: Path):
    transport, operations, events = _runtime(tmp_path)
    envelope = _operation()
    current = operations.create(envelope, now=BASE_TIME)
    current = operations.transition(
        envelope.operation_id,
        OperationState.VALIDATED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    current = operations.transition(
        envelope.operation_id,
        OperationState.AUTHORIZED,
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=2),
    )
    transport.dispatch_pending(envelope.operation_id, tenant_id="tenant-a")
    return transport, operations, events, current


def _full_batch(
    transport: OperationStreamTransport,
    operation_id: str,
) -> OperationStreamBatch:
    return transport.replay(
        operation_id,
        tenant_id="tenant-a",
        after_sequence=0,
        limit=64,
    )


def test_real_durable_replay_reconstructs_authoritative_operation_truth(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    projection = bootstrap_projection(
        current.envelope.operation_id,
        tenant_id="tenant-a",
    )

    decision = apply_stream_batch(
        projection,
        _full_batch(transport, current.envelope.operation_id),
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.after.state is OperationState.AUTHORIZED
    assert decision.after.operation_version == current.version == 3
    assert decision.after.applied_through == 3
    assert decision.after.stream_latest_sequence == 3
    assert decision.after.trace_id == current.envelope.trace_id
    assert decision.after.source is ProjectionSource.REPLAY
    assert decision.after.terminal is False
    assert len(decision.after.truth_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "stream_projection_authority"
    assert evidence.digest == decision.decision_digest

    operations.close()
    events.close()


def test_out_of_order_and_identical_duplicate_page_converges_identically(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = _full_batch(transport, current.envelope.operation_id)
    baseline = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        batch,
    )
    assert baseline.accepted is True

    first, second, third = batch.events
    shuffled = OperationStreamBatch(
        operation=batch.operation,
        events=(third, first, second, second),
        after_sequence=0,
        stream_latest_sequence=batch.stream_latest_sequence,
        stream_terminal=batch.stream_terminal,
    )
    reordered = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        shuffled,
    )

    assert reordered.accepted is True
    assert reordered.after.truth_digest == baseline.after.truth_digest
    assert reordered.after.projection_digest == baseline.after.projection_digest
    assert reordered.input_digest == baseline.input_digest
    assert len(reordered.normalized_event_digests) == 3

    operations.close()
    events.close()


def test_conflicting_duplicate_sequence_fails_without_state_mutation(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = _full_batch(transport, current.envelope.operation_id)
    first = batch.events[0]
    conflict = StreamEvent(
        operation_id=first.operation_id,
        event_id=str(uuid4()),
        sequence=first.sequence,
        type=first.type,
        timestamp=first.timestamp,
        payload={
            **dict(first.payload),
            "trace_id": "different-trace",
        },
    )
    projection = bootstrap_projection(
        current.envelope.operation_id,
        tenant_id="tenant-a",
    )
    malformed = OperationStreamBatch(
        operation=batch.operation,
        events=(first, conflict, *batch.events[1:]),
        after_sequence=0,
        stream_latest_sequence=batch.stream_latest_sequence,
        stream_terminal=batch.stream_terminal,
    )

    decision = apply_stream_batch(projection, malformed)

    assert decision.accepted is False
    assert "conflicting-duplicate-sequence:1" in decision.reasons
    assert decision.after.projection_digest == projection.projection_digest
    with pytest.raises(ProjectionAuthorityError, match="cannot become promotion"):
        decision.accepted_evidence_ref()

    operations.close()
    events.close()


def test_sequence_gap_fails_closed(tmp_path: Path) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = _full_batch(transport, current.envelope.operation_id)
    malformed = OperationStreamBatch(
        operation=batch.operation,
        events=(batch.events[0], batch.events[2]),
        after_sequence=0,
        stream_latest_sequence=batch.stream_latest_sequence,
        stream_terminal=batch.stream_terminal,
    )

    decision = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        malformed,
    )

    assert decision.accepted is False
    assert "sequence-gap:expected-2:got-3" in decision.reasons

    operations.close()
    events.close()


def test_bounded_pages_and_reconnect_cursor_converge_to_full_replay(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    full = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        _full_batch(transport, current.envelope.operation_id),
    )
    assert full.accepted is True

    projection = bootstrap_projection(
        current.envelope.operation_id,
        tenant_id="tenant-a",
    )
    first_page = transport.replay(
        current.envelope.operation_id,
        tenant_id="tenant-a",
        after_sequence=0,
        limit=1,
    )
    first = apply_stream_batch(projection, first_page)
    assert first.accepted is True
    assert first.after.applied_through == 1
    assert first.after.state is OperationState.CREATED
    assert first.after.stream_latest_sequence == 3

    second_page = transport.replay(
        current.envelope.operation_id,
        tenant_id="tenant-a",
        after_sequence=first.after.applied_through,
        limit=64,
    )
    second = apply_stream_batch(first.after, second_page)
    assert second.accepted is True
    assert second.after.truth_digest == full.after.truth_digest
    assert second.after.projection_digest == full.after.projection_digest

    operations.close()
    events.close()


def test_cursor_mismatch_is_rejected(tmp_path: Path) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = transport.replay(
        current.envelope.operation_id,
        tenant_id="tenant-a",
        after_sequence=1,
        limit=64,
    )

    decision = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        batch,
    )

    assert decision.accepted is False
    assert "cursor-mismatch" in decision.reasons

    operations.close()
    events.close()


def test_caught_up_projection_must_match_durable_operation_version_and_state(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = _full_batch(transport, current.envelope.operation_id)
    truncated_head = OperationStreamBatch(
        operation=batch.operation,
        events=(batch.events[0],),
        after_sequence=0,
        stream_latest_sequence=1,
        stream_terminal=False,
    )

    decision = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        truncated_head,
    )

    assert decision.accepted is False
    assert "caught-up-state-mismatch" in decision.reasons
    assert "caught-up-version-mismatch" in decision.reasons

    operations.close()
    events.close()


def test_trace_drift_and_event_type_state_drift_fail_closed(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = _full_batch(transport, current.envelope.operation_id)
    first, second, third = batch.events

    trace_drift = replace(
        second,
        payload={**dict(second.payload), "trace_id": "trace-other"},
    )
    trace_batch = OperationStreamBatch(
        operation=batch.operation,
        events=(first, trace_drift, third),
        after_sequence=0,
        stream_latest_sequence=3,
        stream_terminal=False,
    )
    decision = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        trace_batch,
    )
    assert decision.accepted is False
    assert "trace-id-drift:2" in decision.reasons

    type_drift = replace(second, type="operation.authorized")
    type_batch = replace(
        trace_batch,
        events=(first, type_drift, third),
    )
    decision = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        type_batch,
    )
    assert decision.accepted is False
    assert "event-type-state-mismatch:2" in decision.reasons

    operations.close()
    events.close()


def test_operation_version_gap_fails_closed(tmp_path: Path) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    batch = _full_batch(transport, current.envelope.operation_id)
    first, second, third = batch.events
    version_drift = replace(
        second,
        payload={**dict(second.payload), "version": 7},
    )
    malformed = replace(
        batch,
        events=(first, version_drift, third),
    )

    decision = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        malformed,
    )

    assert decision.accepted is False
    assert "operation-version-gap:expected-2:got-7" in decision.reasons

    operations.close()
    events.close()


def test_authoritative_resync_converges_to_same_truth_as_full_replay(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    full_batch = _full_batch(transport, current.envelope.operation_id)
    replay = apply_stream_batch(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        full_batch,
    )
    assert replay.accepted is True

    events.compact_through(current.envelope.operation_id, 2)
    snapshot = transport.resync_snapshot(
        current.envelope.operation_id,
        tenant_id="tenant-a",
        consumer_id="projection-client",
    )
    resync = apply_resync_snapshot(
        bootstrap_projection(current.envelope.operation_id, tenant_id="tenant-a"),
        snapshot,
    )

    assert resync.accepted is True
    assert resync.after.source is ProjectionSource.RESYNC
    assert resync.after.resync_generation == 1
    assert resync.after.applied_through == snapshot.latest_sequence == 3
    assert resync.after.truth_digest == replay.after.truth_digest
    assert resync.after.projection_digest != replay.after.projection_digest

    operations.close()
    events.close()


def test_resync_rejects_wrong_tenant_and_regressed_head(
    tmp_path: Path,
) -> None:
    transport, operations, events, current = _authorized_runtime(tmp_path)
    projection = bootstrap_projection(
        current.envelope.operation_id,
        tenant_id="tenant-a",
    )
    other = _operation(
        tenant_id="tenant-b",
        operation_id=current.envelope.operation_id,
    )
    other_stored = replace(
        current,
        envelope=other.transition(OperationState.VALIDATED).transition(
            OperationState.AUTHORIZED
        ),
    )
    mismatch = OperationResyncSnapshot(
        operation=other_stored,
        compacted_through=0,
        latest_sequence=3,
        stream_terminal=False,
        active_consumer_count=0,
    )
    decision = apply_resync_snapshot(projection, mismatch)
    assert decision.accepted is False
    assert "resync-tenant-mismatch" in decision.reasons

    caught_up = apply_stream_batch(
        projection,
        _full_batch(transport, current.envelope.operation_id),
    ).after
    regressed = OperationResyncSnapshot(
        operation=current,
        compacted_through=0,
        latest_sequence=2,
        stream_terminal=False,
        active_consumer_count=0,
    )
    decision = apply_resync_snapshot(caught_up, regressed)
    assert decision.accepted is False
    assert "resync-head-regressed" in decision.reasons

    operations.close()
    events.close()


def test_terminal_replay_projects_terminal_once_and_blocks_follow_on_event(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    envelope = _operation()
    operations.create(envelope, now=BASE_TIME)
    transport.cancel(envelope.operation_id, tenant_id="tenant-a")
    batch = _full_batch(transport, envelope.operation_id)

    terminal = apply_stream_batch(
        bootstrap_projection(envelope.operation_id, tenant_id="tenant-a"),
        batch,
    )
    assert terminal.accepted is True
    assert terminal.after.state is OperationState.CANCELLED
    assert terminal.after.terminal is True
    assert terminal.after.operation_version == 2

    impossible = StreamEvent(
        operation_id=envelope.operation_id,
        event_id=str(uuid4()),
        sequence=3,
        type="operation.running",
        timestamp=BASE_TIME + timedelta(seconds=3),
        payload={
            "state": "running",
            "version": 3,
            "trace_id": envelope.trace_id,
        },
    )
    forged_batch = OperationStreamBatch(
        operation=batch.operation,
        events=(impossible,),
        after_sequence=terminal.after.applied_through,
        stream_latest_sequence=3,
        stream_terminal=True,
    )
    rejected = apply_stream_batch(terminal.after, forged_batch)
    assert rejected.accepted is False
    assert "event-after-terminal:3" in rejected.reasons

    operations.close()
    events.close()


def test_projection_constructor_rejects_invented_progress() -> None:
    operation_id = str(uuid4())
    with pytest.raises(ProjectionAuthorityError, match="empty projection"):
        OperationProjection(
            operation_id=operation_id,
            tenant_id="tenant-a",
            state=None,
            operation_version=1,
            applied_through=1,
            stream_latest_sequence=1,
            terminal=False,
            trace_id=None,
            evidence_chain_digest="0" * 64,
        )
