from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest

from core.operation_stream_transport import OperationStreamTransport
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream import StreamReplayGapError
from skeleton.frontier.operation_stream_store_mongo import (
    MongoOperationEventStore,
)
from skeleton.persistence.operation_store import OperationStoreConflict
from skeleton.persistence.operation_store_mongo import MongoOperationStore


pytestmark = pytest.mark.skipif(
    not os.getenv("CODEDOCK_TEST_MONGO_URI"),
    reason="transaction-capable Stage-7 Mongo authority is not configured",
)


def _operation(*, key: str) -> OperationEnvelope:
    now = datetime.now(timezone.utc)
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-stage7",
        actor_id="actor-stage7",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=5),
        idempotency_key=key,
        trace_id="trace-stage7-" + key,
    )


def _advance_to_running(store: MongoOperationStore, operation: OperationEnvelope):
    current = store.create(operation)
    for state in (
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
        OperationState.ADMITTED,
        OperationState.RUNNING,
    ):
        current = store.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
        )
    return current


@pytest.fixture
def mongo_authorities():
    from pymongo import MongoClient

    uri = os.environ["CODEDOCK_TEST_MONGO_URI"]
    database_name = "stage7_operation_authority_" + uuid4().hex
    client_a = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client_b = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client_a.admin.command("ping")
    database_a = client_a[database_name]
    database_b = client_b[database_name]

    operation_a = MongoOperationStore(database_a)
    operation_b = MongoOperationStore(database_b)
    events_a = MongoOperationEventStore(database_a)
    events_b = MongoOperationEventStore(database_b)
    operation_a.ensure_indexes()
    events_a.ensure_indexes()

    try:
        yield operation_a, operation_b, events_a, events_b
    finally:
        client_a.drop_database(database_name)
        client_a.close()
        client_b.close()


def test_mongo_shared_authority_replays_across_workers_and_compacts_by_ack(
    mongo_authorities,
) -> None:
    operation_a, operation_b, events_a, events_b = mongo_authorities
    operation = _operation(key="cross-worker")
    running = _advance_to_running(operation_a, operation)
    completed = operation_a.transition(
        operation.operation_id,
        OperationState.COMPLETED,
        expected_version=running.version,
    )
    assert completed.terminal is True

    worker_a = OperationStreamTransport(
        operation_a,
        events_a,
        worker_id="stage7-worker-a",
    )
    worker_b = OperationStreamTransport(
        operation_b,
        events_b,
        worker_id="stage7-worker-b",
    )

    first = worker_a.replay(
        operation.operation_id,
        tenant_id=operation.tenant_id,
        consumer_id="stage7-browser",
        after_sequence=0,
        limit=2,
    )
    assert [item.sequence for item in first.events] == [1, 2]
    assert first.stream_latest_sequence == 6
    assert first.has_more is True
    assert first.terminal is False

    ack_first = worker_a.acknowledge_and_compact(
        operation.operation_id,
        tenant_id=operation.tenant_id,
        consumer_id="stage7-browser",
        sequence=2,
    )
    assert ack_first.consumer.acknowledged_through == 2
    assert ack_first.compacted_through == 2

    resumed = worker_b.replay(
        operation.operation_id,
        tenant_id=operation.tenant_id,
        consumer_id="stage7-browser",
        after_sequence=2,
        limit=32,
    )
    assert [item.sequence for item in resumed.events] == [3, 4, 5, 6]
    assert resumed.terminal is True
    assert resumed.operation.envelope.state is OperationState.COMPLETED

    ack_terminal = worker_b.acknowledge_and_compact(
        operation.operation_id,
        tenant_id=operation.tenant_id,
        consumer_id="stage7-browser",
        sequence=6,
    )
    assert ack_terminal.compacted_through == 6

    with pytest.raises(StreamReplayGapError):
        worker_a.replay(
            operation.operation_id,
            tenant_id=operation.tenant_id,
            consumer_id="stale-browser",
            after_sequence=0,
            limit=32,
        )


def test_mongo_cancel_complete_race_projects_exactly_one_terminal_event(
    mongo_authorities,
) -> None:
    operation_a, operation_b, events_a, events_b = mongo_authorities
    operation = _operation(key="terminal-race")
    running = _advance_to_running(operation_a, operation)

    cancel_worker = OperationStreamTransport(
        operation_a,
        events_a,
        worker_id="stage7-cancel-worker",
    )
    complete_worker = OperationStreamTransport(
        operation_b,
        events_b,
        worker_id="stage7-complete-worker",
    )

    def cancel() -> str:
        return cancel_worker.cancel(
            operation.operation_id,
            tenant_id=operation.tenant_id,
        ).operation.envelope.state.value

    def complete() -> str:
        try:
            return operation_b.transition(
                operation.operation_id,
                OperationState.COMPLETED,
                expected_version=running.version,
            ).envelope.state.value
        except OperationStoreConflict:
            return operation_b.get(operation.operation_id).envelope.state.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel)
        complete_future = pool.submit(complete)
        observed = {cancel_future.result(), complete_future.result()}

    replay = complete_worker.replay(
        operation.operation_id,
        tenant_id=operation.tenant_id,
        consumer_id="stage7-race-browser",
        after_sequence=0,
        limit=32,
    )
    terminal_events = [
        item
        for item in replay.events
        if item.type in {"operation.completed", "operation.cancelled"}
    ]
    assert len(terminal_events) == 1
    assert replay.operation.envelope.state.value in {"completed", "cancelled"}
    assert terminal_events[0].type == (
        "operation." + replay.operation.envelope.state.value
    )
    assert observed <= {"running", "completed", "cancelled"}
