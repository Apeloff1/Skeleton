from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.inbox_ledger import delivery_from_outbox
from skeleton.persistence.mongo_inbox import MongoInboxLedger
from skeleton.persistence.mongo_projection import MongoSpineProjection
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "13131313-1313-4313-8313-131313131313"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_mongo_projection_advances_once(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(
        OperationEnvelope(
            operation_id=OP,
            tenant_id="tenant-bridge",
            actor_id="actor-bridge",
            capability="chat",
            created_at=BASE,
            deadline=BASE + timedelta(minutes=5),
            idempotency_key="idem-bridge",
            trace_id="trace-bridge",
        ),
        now=BASE,
    )
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    projection = MongoSpineProjection(operations, MongoInboxLedger(None), MongoConsistencyFence())
    first = projection.project(now=BASE + timedelta(seconds=2))
    assert first.applied == 1
    assert first.fence_advances == 1
    second = projection.project(now=BASE + timedelta(seconds=3))
    assert second.duplicates == 1
    assert second.fence_advances == 0
    token = projection.fence.read(tenant_id="tenant-bridge", resource_id=f"op:{OP}")
    assert token.epoch == 1
    assert projection.card(first)["completion_checkbox"] is False
    runtime.close()

def test_mongo_projection_repairs_fence_after_receipt_before_fence(
    tmp_path: Path,
) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(
        OperationEnvelope(
            operation_id=OP,
            tenant_id="tenant-bridge",
            actor_id="actor-bridge",
            capability="chat",
            created_at=BASE,
            deadline=BASE + timedelta(minutes=5),
            idempotency_key="idem-bridge-repair",
            trace_id="trace-bridge-repair",
        ),
        now=BASE,
    )
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    event = operations.published_outbox(
        operation_id=created.envelope.operation_id
    )[0]
    inbox = MongoInboxLedger(None)
    fence = MongoConsistencyFence()
    delivery = delivery_from_outbox(event, "tenant-bridge")
    accepted = inbox.accept(
        delivery,
        consumer_id="mongo-spine",
        now=event.published_at,
    )
    assert accepted.duplicate is False

    projection = MongoSpineProjection(operations, inbox, fence)
    repaired = projection.project(now=BASE + timedelta(seconds=2))
    assert repaired.applied == 0
    assert repaired.duplicates == 1
    assert repaired.poisoned == 0
    assert repaired.fence_advances == 1
    assert fence.read(
        tenant_id="tenant-bridge",
        resource_id=f"op:{OP}",
    ).epoch == 1
    runtime.close()

