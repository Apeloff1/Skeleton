from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from core.operation_stream_transport import OperationStreamTransport
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream import StreamReplayGapError
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import (
    OperationStoreConflict,
    SQLiteOperationStore,
)


BASE_TIME = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)
TENANT = "tenant-multiworker"


def _operation() -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=TENANT,
        actor_id="actor-multiworker",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(hours=1),
        idempotency_key=f"idem-{uuid4()}",
        trace_id=f"trace-{uuid4()}",
    )


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "operations.sqlite3", tmp_path / "events.sqlite3"


def _worker(
    state_path: Path,
    stream_path: Path,
) -> tuple[OperationStreamTransport, SQLiteOperationStore, SQLiteOperationEventStore]:
    operations = SQLiteOperationStore(state_path)
    events = SQLiteOperationEventStore(stream_path)
    return OperationStreamTransport(operations, events), operations, events


def _seed_terminal_operation(
    state_path: Path,
    *,
    terminal: OperationState = OperationState.COMPLETED,
) -> tuple[OperationEnvelope, int]:
    operations = SQLiteOperationStore(state_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    for index, state in enumerate(
        (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
            OperationState.ADMITTED,
            OperationState.RUNNING,
            terminal,
        ),
        start=1,
    ):
        current = operations.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )
    version = current.version
    operations.close()
    return operation, version


def _seed_running_operation(state_path: Path) -> tuple[OperationEnvelope, int]:
    operations = SQLiteOperationStore(state_path)
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
    version = current.version
    operations.close()
    return operation, version


def test_file_backed_operation_and_stream_stores_enable_wal(tmp_path: Path) -> None:
    state_path, stream_path = _paths(tmp_path)
    operations = SQLiteOperationStore(state_path)
    events = SQLiteOperationEventStore(stream_path)

    assert operations._connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert events._connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert operations._connection.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
    assert events._connection.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000

    operations.close()
    events.close()


def test_multiworker_concurrent_outbox_projection_is_exactly_once(
    tmp_path: Path,
) -> None:
    state_path, stream_path = _paths(tmp_path)
    operation, _ = _seed_terminal_operation(state_path)

    workers = [_worker(state_path, stream_path) for _ in range(6)]
    gate = Barrier(len(workers))

    def dispatch(item: tuple[OperationStreamTransport, SQLiteOperationStore, SQLiteOperationEventStore]):
        transport, _, _ = item
        gate.wait(timeout=10)
        return transport.dispatch_pending(
            operation.operation_id,
            tenant_id=TENANT,
            limit=100,
        )

    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        deliveries = list(pool.map(dispatch, workers))

    observer, observer_operations, observer_events = _worker(state_path, stream_path)
    batch = observer.replay(
        operation.operation_id,
        tenant_id=TENANT,
        after_sequence=0,
        limit=100,
    )

    assert [event.sequence for event in batch.events] == [1, 2, 3, 4, 5, 6]
    assert [event.type for event in batch.events] == [
        "operation.created",
        "operation.validated",
        "operation.authorized",
        "operation.admitted",
        "operation.running",
        "operation.completed",
    ]
    assert len({event.event_id for event in batch.events}) == 6
    assert observer_operations.pending_outbox(
        operation_id=operation.operation_id,
        limit=100,
    ) == ()
    assert sum(len(group) for group in deliveries) >= 6

    for _, operations, events in workers:
        operations.close()
        events.close()
    observer_operations.close()
    observer_events.close()


def test_multiworker_consumer_checkpoints_share_one_compaction_floor(
    tmp_path: Path,
) -> None:
    state_path, stream_path = _paths(tmp_path)
    operation, _ = _seed_terminal_operation(state_path)
    worker_a, operations_a, events_a = _worker(state_path, stream_path)
    worker_b, operations_b, events_b = _worker(state_path, stream_path)

    first = worker_a.replay(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-a",
        after_sequence=0,
        limit=100,
    )
    second = worker_b.replay(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-b",
        after_sequence=0,
        limit=100,
    )
    assert first.latest_sequence == second.latest_sequence == 6

    fast = worker_a.acknowledge_and_compact(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-a",
        sequence=6,
    )
    assert fast.compacted_through == 0
    assert fast.active_consumer_count == 2

    slow = worker_b.acknowledge_and_compact(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-b",
        sequence=2,
    )
    assert slow.compacted_through == 2
    assert slow.compacted_events == 2

    with pytest.raises(StreamReplayGapError):
        worker_a.replay(
            operation.operation_id,
            tenant_id=TENANT,
            after_sequence=1,
            limit=100,
        )

    caught_up = worker_b.acknowledge_and_compact(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-b",
        sequence=6,
    )
    assert caught_up.compacted_through == 6
    assert caught_up.latest_sequence == 6

    operations_a.close()
    events_a.close()
    operations_b.close()
    events_b.close()


def test_disconnect_reconnect_hands_cursor_to_another_worker_without_duplicates(
    tmp_path: Path,
) -> None:
    state_path, stream_path = _paths(tmp_path)
    operation, _ = _seed_terminal_operation(state_path)
    worker_a, operations_a, events_a = _worker(state_path, stream_path)

    first_page = worker_a.replay(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-resume",
        after_sequence=0,
        limit=2,
    )
    assert [event.sequence for event in first_page.events] == [1, 2]
    assert first_page.has_more is True

    checkpoint = worker_a.acknowledge(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-resume",
        sequence=2,
    )
    assert checkpoint.acknowledged_through == 2
    operations_a.close()
    events_a.close()

    worker_b, operations_b, events_b = _worker(state_path, stream_path)
    resumed = worker_b.replay(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-resume",
        after_sequence=2,
        limit=100,
    )

    assert [event.sequence for event in resumed.events] == [3, 4, 5, 6]
    assert resumed.terminal is True
    assert len({event.event_id for event in first_page.events + resumed.events}) == 6

    final_ack = worker_b.acknowledge_and_compact(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-resume",
        sequence=6,
    )
    assert final_ack.compacted_through == 6

    operations_b.close()
    events_b.close()


def test_multiworker_cancel_complete_race_emits_one_terminal_event(
    tmp_path: Path,
) -> None:
    state_path, stream_path = _paths(tmp_path)
    operation, running_version = _seed_running_operation(state_path)

    cancel_worker, cancel_operations, cancel_events = _worker(state_path, stream_path)
    complete_worker, complete_operations, complete_events = _worker(state_path, stream_path)
    gate = Barrier(2)

    def cancel() -> str:
        gate.wait(timeout=10)
        result = cancel_worker.cancel(operation.operation_id, tenant_id=TENANT)
        return result.operation.envelope.state.value

    def complete() -> str:
        gate.wait(timeout=10)
        try:
            completed = complete_operations.transition(
                operation.operation_id,
                OperationState.COMPLETED,
                expected_version=running_version,
                now=BASE_TIME + timedelta(seconds=10),
            )
        except OperationStoreConflict:
            return complete_operations.get(operation.operation_id).envelope.state.value
        complete_worker.dispatch_pending(operation.operation_id, tenant_id=TENANT)
        return completed.envelope.state.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel)
        complete_future = pool.submit(complete)
        observed_states = {cancel_future.result(), complete_future.result()}

    observer, observer_operations, observer_events = _worker(state_path, stream_path)
    batch = observer.replay(
        operation.operation_id,
        tenant_id=TENANT,
        after_sequence=0,
        limit=100,
    )
    terminal_events = [
        event for event in batch.events
        if event.type in {"operation.completed", "operation.cancelled"}
    ]

    assert len(terminal_events) == 1
    final_state = batch.operation.envelope.state.value
    assert final_state in {"completed", "cancelled"}
    assert terminal_events[0].type == f"operation.{final_state}"
    assert observed_states <= {"running", "completed", "cancelled"}
    assert batch.terminal is True

    cancel_operations.close()
    cancel_events.close()
    complete_operations.close()
    complete_events.close()
    observer_operations.close()
    observer_events.close()


def test_consumer_checkpoint_survives_worker_restart_and_lease_renewal(
    tmp_path: Path,
) -> None:
    state_path, stream_path = _paths(tmp_path)
    operation, _ = _seed_terminal_operation(state_path)
    worker_a, operations_a, events_a = _worker(state_path, stream_path)

    page = worker_a.replay(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-restart",
        after_sequence=0,
        limit=3,
    )
    assert [event.sequence for event in page.events] == [1, 2, 3]
    worker_a.acknowledge(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-restart",
        sequence=3,
    )
    operations_a.close()
    events_a.close()

    worker_b, operations_b, events_b = _worker(state_path, stream_path)
    checkpoints = events_b.active_consumers(operation.operation_id)
    assert len(checkpoints) == 1
    assert checkpoints[0].consumer_id == "browser-restart"
    assert checkpoints[0].acknowledged_through == 3

    resumed = worker_b.replay(
        operation.operation_id,
        tenant_id=TENANT,
        consumer_id="browser-restart",
        after_sequence=3,
        limit=100,
    )
    assert [event.sequence for event in resumed.events] == [4, 5, 6]

    operations_b.close()
    events_b.close()
