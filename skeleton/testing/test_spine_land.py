from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_land import SpineLand
from skeleton.persistence.spine_projection import SpineProjection


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_spine_land_dispatches_then_projects(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    envelope = OperationEnvelope(
        operation_id="22222222-2222-4222-8222-222222222222",
        tenant_id="tenant-land",
        actor_id="actor-land",
        capability="chat",
        created_at=BASE,
        deadline=BASE + timedelta(minutes=5),
        idempotency_key="idem-land",
        trace_id="trace-land",
    )
    created = operations.create(envelope, now=BASE)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        land = SpineLand(runtime, inbox, fence, projection)
        report = land.project_published(operation_id=created.envelope.operation_id)
        assert report.dispatch.published == 1
        assert report.projection.applied == 1
        assert report.projection.fence_advances == 1
        replay = land.project_published(operation_id=created.envelope.operation_id)
        assert replay.dispatch.published == 0
        assert replay.projection.duplicates == 1
        card = land.card(report)
        assert card["stored_prose"] == 0
        assert card["completion_checkbox"] is False
    runtime.close()
