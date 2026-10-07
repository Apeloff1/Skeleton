from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_cutover import SpineCutover
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_gap import SpineGap
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_seal import SpineSeal


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "17171717-1717-4717-8717-171717171717"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_seal_and_gap(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(
        OperationEnvelope(
            operation_id=OP,
            tenant_id="tenant-seal",
            actor_id="actor-seal",
            capability="chat",
            created_at=BASE,
            deadline=BASE + timedelta(minutes=5),
            idempotency_key="idem-seal",
            trace_id="trace-seal",
        ),
        now=BASE,
    )
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    cutover = SpineCutover(
        SpineLag(operations),
        SpineDrift(SQLiteConsistencyFence(":memory:"), MongoConsistencyFence()),
        SpineApplyGate(),
    )
    seal = SpineSeal(tmp_path / "seal.sqlite", cutover)
    card = seal.seal(tenant_id="tenant-seal", operation_id=OP, now=BASE)
    assert card["seal_id"] == 1
    assert card["applied"] == 0
    assert seal.count() == 1
    gap = SpineGap(operations, inbox).read(operation_id=OP)
    assert gap["applied_through"] == 0
    assert gap["missing"] == [1]
    assert gap["completion_checkbox"] is False
    seal.close()
    runtime.close()
