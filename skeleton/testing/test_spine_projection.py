from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import (
    SQLiteInboxLedger,
    delivery_from_outbox,
)
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_projection import SpineProjection


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 0.9}


def _envelope() -> OperationEnvelope:
    return OperationEnvelope(
        operation_id="11111111-1111-4111-8111-111111111111",
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="chat",
        created_at=BASE,
        deadline=BASE + timedelta(minutes=5),
        idempotency_key="idem-spine",
        trace_id="trace-spine",
    )


def test_projection_accepts_published_outbox_and_advances_fence(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(_envelope(), now=BASE)
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    published = operations.published_outbox(operation_id=created.envelope.operation_id)
    assert len(published) == 1

    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(
        operations,
        inbox,
        fence,
        journal_path=tmp_path / "journal.sqlite",
    ) as projection:
        first = projection.project(now=BASE + timedelta(seconds=5))
        assert first.applied == 1
        assert first.fence_advances == 1
        assert first.poisoned == 0
        again = projection.project(now=BASE + timedelta(seconds=6))
        assert again.applied == 0
        assert again.duplicates == 1
        assert again.fence_advances == 0
        token = fence.read(
            tenant_id="tenant-a",
            resource_id=f"op:{created.envelope.operation_id}",
        )
        assert token.epoch == 1
        card = projection.card()
        assert card["stored_prose"] == 0
        assert card["completion_checkbox"] is False
    runtime.close()

def test_projection_repairs_fence_after_receipt_committed_before_fence(
    tmp_path: Path,
) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(_envelope(), now=BASE)
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    event = operations.published_outbox(
        operation_id=created.envelope.operation_id
    )[0]

    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    delivery = delivery_from_outbox(event, "tenant-a")
    accepted = inbox.accept(
        delivery,
        consumer_id="spine-projection",
        now=event.published_at,
    )
    assert accepted.duplicate is False

    with SpineProjection(
        operations,
        inbox,
        fence,
        journal_path=tmp_path / "journal.sqlite",
    ) as projection:
        repaired = projection.project(now=BASE + timedelta(seconds=5))
        assert repaired.applied == 0
        assert repaired.duplicates == 1
        assert repaired.poisoned == 0
        assert repaired.fence_advances == 1
        assert fence.read(
            tenant_id="tenant-a",
            resource_id=f"op:{created.envelope.operation_id}",
        ).epoch == 1
    runtime.close()


def test_projection_fails_closed_when_fence_is_ahead_of_inbox(
    tmp_path: Path,
) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(_envelope(), now=BASE)
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)
    event = operations.published_outbox(
        operation_id=created.envelope.operation_id
    )[0]

    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    delivery = delivery_from_outbox(event, "tenant-a")
    inbox.accept(
        delivery,
        consumer_id="spine-projection",
        now=event.published_at,
    )
    resource = f"op:{created.envelope.operation_id}"
    fence.open(
        tenant_id="tenant-a",
        resource_id=resource,
        writer_id="other-writer",
        now=event.published_at,
    )
    fence.compare_and_advance(
        tenant_id="tenant-a",
        resource_id=resource,
        expected_epoch=1,
        writer_id="other-writer",
        now=event.published_at + timedelta(seconds=1),
    )

    with SpineProjection(
        operations,
        inbox,
        fence,
        journal_path=tmp_path / "journal.sqlite",
    ) as projection:
        report = projection.project(now=BASE + timedelta(seconds=5))
        assert report.applied == 0
        assert report.duplicates == 0
        assert report.poisoned == 1
        assert report.fence_advances == 0
        assert projection.poison_count() == 1
    runtime.close()

