from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_cutover import SpineCutover
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_window import SpineWindow


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "16161616-1616-4616-8616-161616161616"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_cutover_and_window(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(
        OperationEnvelope(
            operation_id=OP,
            tenant_id="tenant-cut",
            actor_id="actor-cut",
            capability="chat",
            created_at=BASE,
            deadline=BASE + timedelta(minutes=5),
            idempotency_key="idem-cut",
            trace_id="trace-cut",
        ),
        now=BASE,
    )
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    window = SpineWindow(operations)
    assert window.card(tenant_id="tenant-cut")["count"] == 1
    assert window.card(tenant_id="tenant-other")["count"] == 0
    cutover = SpineCutover(
        SpineLag(operations),
        SpineDrift(SQLiteConsistencyFence(":memory:"), MongoConsistencyFence()),
        SpineApplyGate(),
    )
    card = cutover.card(tenant_id="tenant-cut", operation_id=OP)
    assert card["pending"] == 0
    assert card["published"] == 1
    assert card["sqlite_epoch"] == 0
    assert card["mongo_epoch"] == 0
    assert card["applied"] == 0
    assert card["apply_refused"] is True
    assert card["apply_refusal_count"] == 0
    assert card["hit"] is True
    assert card["completion_checkbox"] is False
    runtime.close()
