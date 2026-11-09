from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_batch import SpineBatch
from skeleton.persistence.spine_catalog import SpineCatalog
from skeleton.persistence.spine_cursor import SpineCursorRead
from skeleton.persistence.spine_dispatch import SpineDispatchHook
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_projection import SpineProjection
from skeleton.persistence.spine_status import SpineStatus
from skeleton.persistence.spine_witness import SpineWitness


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "15151515-1515-4515-8515-151515151515"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_batch_and_witness(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    operations.create(
        OperationEnvelope(
            operation_id=OP,
            tenant_id="tenant-mass",
            actor_id="actor-mass",
            capability="chat",
            created_at=BASE,
            deadline=BASE + timedelta(minutes=5),
            idempotency_key="idem-mass",
            trace_id="trace-mass",
        ),
        now=BASE,
    )
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        hook = SpineDispatchHook(runtime, projection, SpineCursorRead(projection, fence))
        report = SpineBatch(hook).run((OP,), tenant_id="tenant-mass", now=BASE + timedelta(seconds=2))
        assert report.succeeded == 1
        assert report.failed == 0
        assert report.as_dict()["completion_checkbox"] is False
        witness = SpineWitness(
            SpineLag(operations),
            SpineCatalog(fence),
            SpineStatus(projection, inbox, fence),
        )
        card = witness.card(tenant_id="tenant-mass", operation_id=OP)
        assert card["pending"] == 0
        assert card["published"] == 1
        assert card["fence_epoch"] == 1
        assert card["catalog_count"] == 1
        assert card["completion_checkbox"] is False
    runtime.close()
