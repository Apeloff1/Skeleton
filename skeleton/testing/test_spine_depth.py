from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import (
    ConsistencyFenceError,
    SQLiteConsistencyFence,
)
from skeleton.persistence.inbox_ledger import (
    InboxConflict,
    InboxDelivery,
    SQLiteInboxLedger,
)
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_depth import SpineProjection


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "33333333-3333-4333-8333-333333333333"


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def _envelope() -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=OP,
        tenant_id="tenant-deep",
        actor_id="actor-deep",
        capability="chat",
        created_at=BASE,
        deadline=BASE + timedelta(minutes=5),
        idempotency_key="idem-deep",
        trace_id="trace-deep",
    )


def _delivery(version: int, payload: dict[str, int]) -> InboxDelivery:
    return InboxDelivery(
        event_id="44444444-4444-4444-8444-444444444444",
        operation_id=OP,
        operation_version=version,
        event_type="operation.created",
        payload=payload,
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-deep",
    )


def test_inbox_rejects_version_gap() -> None:
    inbox = SQLiteInboxLedger(":memory:")
    inbox.accept(_delivery(1, {"n": 1}), consumer_id="deep", now=BASE)
    with pytest.raises(InboxConflict):
        inbox.accept(
            InboxDelivery(
                event_id="55555555-5555-4555-8555-555555555555",
                operation_id=OP,
                operation_version=3,
                event_type="operation.created",
                payload={"n": 3},
                created_at=BASE,
                published_at=BASE,
                tenant_id="tenant-deep",
            ),
            consumer_id="deep",
            now=BASE,
        )


def test_fence_hides_foreign_tenant() -> None:
    fence = SQLiteConsistencyFence(":memory:")
    fence.compare_and_advance(
        tenant_id="tenant-deep",
        resource_id=f"op:{OP}",
        expected_epoch=0,
        writer_id="deep",
        now=BASE,
    )
    with pytest.raises(ConsistencyFenceError):
        fence.read(tenant_id="tenant-other", resource_id=f"op:{OP}")


def test_poison_replay_does_not_advance_fence(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(_envelope(), now=BASE)
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    published = operations.published_outbox(operation_id=OP)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    inbox.accept(
        _delivery(1, {"conflict": 1}),
        consumer_id="spine-projection",
        now=BASE,
    )
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        report = projection.project(now=BASE + timedelta(seconds=1))
        assert report.poisoned == 1
        assert report.fence_advances == 0
        marks = projection.replay_poison()
        assert len(marks) == 1
        assert marks[0].outbox_id == published[0].outbox_id
        assert marks[0].as_dict()["completion_checkbox"] is False
        with pytest.raises(ConsistencyFenceError):
            fence.read(tenant_id="tenant-deep", resource_id=f"op:{OP}")
    runtime.close()
