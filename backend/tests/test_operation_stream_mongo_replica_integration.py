from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.core.operation_stream_transport import OperationStreamTransport
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream_store_mongo import (
    MongoOperationEventStore,
)
from skeleton.persistence.operation_store_mongo import MongoOperationStore


pytestmark = pytest.mark.skipif(
    not os.environ.get("CODEDOCK_TEST_MONGO_URI"),
    reason="CODEDOCK_TEST_MONGO_URI is required for live replica-set evidence",
)


def _operation() -> OperationEnvelope:
    now = datetime.now(timezone.utc)
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-stage7",
        actor_id="actor-stage7",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=5),
        idempotency_key="stage7-mongo-" + uuid4().hex,
        trace_id="trace-stage7-mongo-" + uuid4().hex,
    )


def _stores(database):
    operations = MongoOperationStore(database)
    events = MongoOperationEventStore(database)
    operations.ensure_indexes()
    events.ensure_indexes()
    events.validate_transaction_capability()
    return operations, events


def test_real_replica_set_preserves_cross_client_stream_authority() -> None:
    pymongo = pytest.importorskip("pymongo")
    uri = os.environ["CODEDOCK_TEST_MONGO_URI"].strip()
    database_name = "stage7_operation_" + uuid4().hex

    client_a = pymongo.MongoClient(
        uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
    )
    client_b = pymongo.MongoClient(
        uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
    )

    try:
        database_a = client_a[database_name]
        database_b = client_b[database_name]
        operations_a, events_a = _stores(database_a)
        operations_b, events_b = _stores(database_b)

        worker_a = OperationStreamTransport(
            operations_a,
            events_a,
            worker_id="stage7-mongo-worker-a",
            projection_lease_seconds=5,
        )
        worker_b = OperationStreamTransport(
            operations_b,
            events_b,
            worker_id="stage7-mongo-worker-b",
            projection_lease_seconds=5,
        )

        operation = _operation()
        created = operations_a.create(operation)
        validated = operations_a.transition(
            operation.operation_id,
            OperationState.VALIDATED,
            expected_version=created.version,
        )
        admitted = operations_a.transition(
            operation.operation_id,
            OperationState.ADMITTED,
            expected_version=validated.version,
        )
        running = operations_a.transition(
            operation.operation_id,
            OperationState.RUNNING,
            expected_version=admitted.version,
        )

        first = worker_a.replay(
            operation.operation_id,
            tenant_id=operation.tenant_id,
            after_sequence=0,
            limit=2,
            consumer_id="stage7-browser",
            consumer_lease_seconds=60,
        )
        assert [event.sequence for event in first.events] == [1, 2]
        assert first.has_more is True
        assert first.terminal is False

        worker_a.acknowledge(
            operation.operation_id,
            tenant_id=operation.tenant_id,
            consumer_id="stage7-browser",
            sequence=2,
            consumer_lease_seconds=60,
        )

        completed = operations_b.transition(
            operation.operation_id,
            OperationState.COMPLETED,
            expected_version=running.version,
        )
        assert completed.terminal is True

        resumed = worker_b.replay(
            operation.operation_id,
            tenant_id=operation.tenant_id,
            after_sequence=2,
            limit=16,
            consumer_id="stage7-browser",
            consumer_lease_seconds=60,
        )
        assert [event.sequence for event in resumed.events] == [3, 4, 5]
        assert resumed.terminal is True
        assert resumed.has_more is False
        assert resumed.operation.envelope.state is OperationState.COMPLETED

        acknowledgement = worker_b.acknowledge_and_compact(
            operation.operation_id,
            tenant_id=operation.tenant_id,
            consumer_id="stage7-browser",
            sequence=5,
            consumer_lease_seconds=60,
        )
        assert acknowledgement.consumer.acknowledged_through == 5
        assert acknowledgement.compacted_through == 5

        # A third authority view must observe the compacted terminal state
        # without depending on either worker's in-memory lifetime.
        operations_c, events_c = _stores(client_a[database_name])
        worker_c = OperationStreamTransport(
            operations_c,
            events_c,
            worker_id="stage7-mongo-worker-c",
            projection_lease_seconds=5,
        )
        snapshot = worker_c.resync_snapshot(
            operation.operation_id,
            tenant_id=operation.tenant_id,
            consumer_id="stage7-browser-reconnected",
            consumer_lease_seconds=60,
        )
        assert snapshot.operation.envelope.state is OperationState.COMPLETED
        assert snapshot.stream_terminal is True
        assert snapshot.latest_sequence == 5
        assert snapshot.compacted_through == 5
    finally:
        client_a.drop_database(database_name)
        client_a.close()
        client_b.close()
