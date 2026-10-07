from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_cursor import SpineCursorRead
from skeleton.persistence.spine_dispatch import SpineDispatchError, SpineDispatchHook
from skeleton.persistence.spine_projection import SpineProjection


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "66666666-6666-4666-8666-666666666666"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def _envelope() -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=OP,
        tenant_id="tenant-hook",
        actor_id="actor-hook",
        capability="chat",
        created_at=BASE,
        deadline=BASE + timedelta(minutes=5),
        idempotency_key="idem-hook",
        trace_id="trace-hook",
    )


def test_dispatch_hook_projects_and_reads_cursor(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(_envelope(), now=BASE)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    resource = f"op:{OP}"
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        cursor = SpineCursorRead(projection, fence)
        hook = SpineDispatchHook(runtime, projection, cursor)
        first = hook.run(
            operation_id=created.envelope.operation_id,
            tenant_id="tenant-hook",
            resource_id=resource,
            now=BASE + timedelta(seconds=2),
        )
        assert first.dispatch.published == 1
        assert first.projection.applied == 1
        assert first.cursor.applied_count == 1
        assert first.cursor.fence_epoch == 1
        assert first.cursor.poison_count == 0
        second = hook.run(
            operation_id=created.envelope.operation_id,
            tenant_id="tenant-hook",
            resource_id=resource,
            now=BASE + timedelta(seconds=3),
        )
        assert second.dispatch.published == 0
        assert second.projection.duplicates == 1
        assert second.projection.fence_advances == 0
        assert second.projection.reconciled == 0
        assert second.cursor.fence_epoch == 1
        card = hook.card(second)
        assert card["stored_prose"] == 0
        assert card["completion_checkbox"] is False
        assert card["attempts"] == 2
    runtime.close()


def test_dispatch_hook_rejects_naive_time(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence) as projection:
        hook = SpineDispatchHook(runtime, projection, SpineCursorRead(projection, fence))
        with pytest.raises(SpineDispatchError):
            hook.run(now=datetime(2026, 9, 21, 12, 0))
    runtime.close()
