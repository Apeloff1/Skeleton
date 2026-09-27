"""Stage-7 real Mongo shared-authority integration and fault journey."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from core.operation_stream_transport import OperationStreamTransport
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream_store_mongo import MongoOperationEventStore
from skeleton.persistence.operation_store_mongo import MongoOperationStore


pytestmark = pytest.mark.skipif(
    not os.environ.get("STAGE7_MONGO_URI"),
    reason="STAGE7_MONGO_URI is required for real Mongo Stage-7 integration",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _operation(operation_id: str, now: datetime) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=operation_id,
        tenant_id="tenant-stage7",
        actor_id="actor-stage7",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=5),
        idempotency_key="stage7-mongo-idempotency",
        trace_id="trace-stage7-mongo",
    )


def test_stage7_mongo_shared_authority_survives_transient_update_failure() -> None:
    uri = os.environ["STAGE7_MONGO_URI"]
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
        retryWrites=False,
    )
    database_name = "stage7_golden_" + uuid4().hex
    database = client[database_name]
    namespace = "stage7-" + uuid4().hex
    operation_id = "op-" + uuid4().hex
    started = _now()

    operations = MongoOperationStore(
        database,
        namespace=namespace,
        collection="operations",
    )
    events = MongoOperationEventStore(
        database,
        namespace=namespace,
        collection_prefix="stream",
        capacity_per_operation=32,
    )
    operations.ensure_indexes()
    events.ensure_indexes()

    try:
        created = operations.create(_operation(operation_id, started), now=started)
        assert created.version == 1
        assert created.envelope.state is OperationState.CREATED

        worker_a = OperationStreamTransport(
            operations,
            events,
            worker_id="stage7-worker-a",
        )
        first = worker_a.replay(
            operation_id,
            tenant_id="tenant-stage7",
            consumer_id="browser-a",
        )
        assert [item.type for item in first.events] == ["operation.created"]
        assert first.latest_sequence == 1

        running = operations.transition(
            operation_id,
            OperationState.RUNNING,
            expected_version=1,
            now=started + timedelta(seconds=1),
        )
        assert running.version == 2

        worker_b = OperationStreamTransport(
            operations,
            events,
            worker_id="stage7-worker-b",
        )
        second = worker_b.replay(
            operation_id,
            tenant_id="tenant-stage7",
            after_sequence=1,
            consumer_id="browser-b",
        )
        assert [item.type for item in second.events] == ["operation.running"]
        assert second.latest_sequence == 2

        client.admin.command(
            {
                "configureFailPoint": "failCommand",
                "mode": {"times": 1},
                "data": {
                    "failCommands": ["update"],
                    "errorCode": 91,
                    "errorLabels": ["RetryableWriteError"],
                },
            }
        )
        with pytest.raises(PyMongoError):
            operations.transition(
                operation_id,
                OperationState.COMPLETED,
                expected_version=2,
                now=started + timedelta(seconds=2),
            )

        unchanged = operations.get(operation_id)
        assert unchanged.version == 2
        assert unchanged.envelope.state is OperationState.RUNNING
        pending = operations.pending_outbox(operation_id=operation_id)
        # Both created/running outbox rows were already projected and ACKed.
        # A failed completion transition must not leave any new partial outbox
        # publication intent behind.
        assert pending == ()

        completed = operations.transition(
            operation_id,
            OperationState.COMPLETED,
            expected_version=2,
            now=started + timedelta(seconds=3),
        )
        assert completed.version == 3
        assert completed.envelope.state is OperationState.COMPLETED

        terminal = worker_a.replay(
            operation_id,
            tenant_id="tenant-stage7",
            after_sequence=2,
            consumer_id="browser-a",
        )
        assert [item.type for item in terminal.events] == ["operation.completed"]
        assert terminal.latest_sequence == 3
        assert terminal.terminal is True

        acknowledgement = worker_a.acknowledge_and_compact(
            operation_id,
            tenant_id="tenant-stage7",
            consumer_id="browser-a",
            sequence=3,
        )
        assert acknowledgement.consumer.acknowledged_through == 3
        assert acknowledgement.latest_sequence == 3

        cancelled = worker_b.cancel(
            operation_id,
            tenant_id="tenant-stage7",
        )
        assert cancelled.changed is False
        assert cancelled.operation.envelope.state is OperationState.COMPLETED

        assert operations.pending_outbox(operation_id=operation_id) == ()
        head = events.head(operation_id)
        assert head["latest_sequence"] == 3
        assert head["terminal"] is True
    finally:
        try:
            client.admin.command(
                {
                    "configureFailPoint": "failCommand",
                    "mode": "off",
                }
            )
        except PyMongoError:
            pass
        client.drop_database(database_name)
        client.close()
