from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.mongo_catalog import MongoCatalog
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_catalog import SpineCatalog
from skeleton.persistence.spine_lag import SpineLag


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "14141414-1414-4414-8414-141414141414"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_lag_drops_after_dispatch(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(
        OperationEnvelope(
            operation_id=OP,
            tenant_id="tenant-lag",
            actor_id="actor-lag",
            capability="chat",
            created_at=BASE,
            deadline=BASE + timedelta(minutes=5),
            idempotency_key="idem-lag",
            trace_id="trace-lag",
        ),
        now=BASE,
    )
    before = SpineLag(operations).read(operation_id=OP)
    assert before["pending"] == 1
    assert before["published"] == 0
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    after = SpineLag(operations).read(operation_id=OP)
    assert after["pending"] == 0
    assert after["published"] == 1
    assert after["completion_checkbox"] is False
    runtime.close()


def test_catalogs_hide_other_tenants() -> None:
    fence = SQLiteConsistencyFence(":memory:")
    fence.compare_and_advance(
        tenant_id="tenant-lag",
        resource_id=f"op:{OP}",
        expected_epoch=0,
        writer_id="lag",
        now=BASE,
    )
    catalog = SpineCatalog(fence)
    assert catalog.card(tenant_id="tenant-lag")["count"] == 1
    assert catalog.card(tenant_id="tenant-other")["count"] == 0
    mongo = MongoConsistencyFence()
    mongo.compare_and_advance(
        tenant_id="tenant-lag",
        resource_id=f"op:{OP}",
        expected_epoch=0,
        writer_id="lag",
        now=BASE,
    )
    listed = MongoCatalog(mongo).list(tenant_id="tenant-lag")
    assert listed[0]["epoch"] == 1
    assert MongoCatalog(mongo).card(tenant_id="tenant-other")["count"] == 0
