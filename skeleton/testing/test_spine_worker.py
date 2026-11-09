from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_cursor import SpineCursorRead
from skeleton.persistence.spine_dispatch import SpineDispatchHook
from skeleton.persistence.spine_projection import SpineProjection
from skeleton.persistence.spine_worker import SpineWorker


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def test_worker_drains_without_replacing_runtime(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    envelope = OperationEnvelope(
        operation_id="12121212-1212-4212-8212-121212121212",
        tenant_id="tenant-worker",
        actor_id="actor-worker",
        capability="chat",
        created_at=BASE,
        deadline=BASE + timedelta(minutes=5),
        idempotency_key="idem-worker",
        trace_id="trace-worker",
    )
    operations.create(envelope, now=BASE)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        hook = SpineDispatchHook(runtime, projection, SpineCursorRead(projection, fence))
        worker = SpineWorker(hook, interval_s=0.05)
        assert worker.start() is True
        assert worker.start() is False
        time.sleep(0.2)
        card = worker.stop()
        assert card["hit"] is True
        assert card["completion_checkbox"] is False
        assert hook.attempts >= 1
    runtime.close()
