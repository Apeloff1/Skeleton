from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import (
    SQLiteInboxLedger,
    delivery_from_outbox,
)
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_cursor import SpineCursorRead
from skeleton.persistence.spine_projection import SpineProjection
from skeleton.persistence.spine_quarantine import SpineQuarantine


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
        assert repaired.reconciled == 1
        cursor = SpineCursorRead(projection, fence).read(
            tenant_id="tenant-a",
            resource_id=f"op:{created.envelope.operation_id}",
        )
        assert cursor.applied_count == 1
        assert cursor.fence_epoch == 1
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

def test_projection_recovers_cursor_after_fence_committed_before_completion(
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
    resource = f"op:{created.envelope.operation_id}"
    fence.open(
        tenant_id="tenant-a",
        resource_id=resource,
        writer_id="spine-projection",
        now=event.published_at,
    )

    with SpineProjection(
        operations,
        inbox,
        fence,
        journal_path=tmp_path / "journal.sqlite",
    ) as projection:
        repaired = projection.project(now=BASE + timedelta(seconds=5))
        assert repaired.applied == 0
        assert repaired.duplicates == 1
        assert repaired.fence_advances == 0
        assert repaired.reconciled == 1
        cursor = SpineCursorRead(projection, fence).read(
            tenant_id="tenant-a",
            resource_id=resource,
        )
        assert cursor.applied_count == 1
        assert cursor.fence_epoch == 1

        replay = projection.project(now=BASE + timedelta(seconds=6))
        assert replay.duplicates == 1
        assert replay.reconciled == 0
        assert SpineCursorRead(projection, fence).read(
            tenant_id="tenant-a",
            resource_id=resource,
        ).applied_count == 1
    runtime.close()

def test_projection_rebuilds_legacy_aggregate_cursor_from_completion_evidence(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.sqlite"
    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        CREATE TABLE projection_cursor (
            consumer_id TEXT PRIMARY KEY,
            applied_count INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO projection_cursor(
            consumer_id, applied_count, updated_at
        ) VALUES (?, ?, ?)
        """,
        ("spine-projection", 7, BASE.isoformat()),
    )
    connection.commit()
    connection.close()

    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(
        operations,
        inbox,
        fence,
        journal_path=journal_path,
    ) as projection:
        cursor = SpineCursorRead(projection, fence).read()
        assert cursor.applied_count == 0


def test_projection_completion_identity_is_scoped_by_consumer(
    tmp_path: Path,
) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    created = operations.create(_envelope(), now=BASE)
    runtime.dispatch_outbox(operation_id=created.envelope.operation_id)

    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    journal_path = tmp_path / "journal.sqlite"
    with SpineProjection(
        operations,
        inbox,
        fence,
        consumer_id="projection-a",
        journal_path=journal_path,
    ) as first:
        first_report = first.project(now=BASE + timedelta(seconds=2))
        assert first_report.applied == 1
        assert SpineCursorRead(first, fence).read().applied_count == 1

    with SpineProjection(
        operations,
        inbox,
        fence,
        consumer_id="projection-b",
        journal_path=journal_path,
    ) as second:
        second_report = second.project(now=BASE + timedelta(seconds=3))
        assert second_report.applied == 1
        assert second_report.fence_advances == 0
        assert SpineCursorRead(second, fence).read().applied_count == 1

    connection = sqlite3.connect(journal_path)
    rows = connection.execute(
        """
        SELECT consumer_id
        FROM projection_applied
        ORDER BY consumer_id
        """
    ).fetchall()
    connection.close()
    assert rows == [("projection-a",), ("projection-b",)]
    runtime.close()

def test_projection_migrates_legacy_poison_rows_to_current_consumer(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.sqlite"
    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        CREATE TABLE projection_poison (
            outbox_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            digest TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO projection_poison(
            outbox_id, operation_id, tenant_id, reason, digest, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-outbox",
            "legacy-operation",
            "tenant-a",
            "LegacyConflict",
            "d" * 64,
            BASE.isoformat(),
        ),
    )
    connection.commit()
    connection.close()

    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(
        operations,
        inbox,
        fence,
        consumer_id="legacy-consumer",
        journal_path=journal_path,
    ) as projection:
        assert projection.poison_count() == 1
        marks = SpineQuarantine(projection).list(tenant_id="tenant-a")
        assert len(marks) == 1
        assert marks[0].outbox_id == "legacy-outbox"


def test_projection_poison_quarantine_is_scoped_by_consumer(
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
    delivery = delivery_from_outbox(event, "tenant-a")

    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    inbox.accept(
        replace(delivery, payload={"tampered": True}),
        consumer_id="projection-a",
        now=event.published_at,
    )
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    journal_path = tmp_path / "journal.sqlite"

    with SpineProjection(
        operations,
        inbox,
        fence,
        consumer_id="projection-a",
        journal_path=journal_path,
    ) as first:
        failed = first.project(now=BASE + timedelta(seconds=2))
        assert failed.poisoned == 1
        assert first.poison_count() == 1
        assert SpineCursorRead(first, fence).read().poison_count == 1
        assert SpineQuarantine(first).card("tenant-a")["count"] == 1

    with SpineProjection(
        operations,
        inbox,
        fence,
        consumer_id="projection-b",
        journal_path=journal_path,
    ) as second:
        accepted = second.project(now=BASE + timedelta(seconds=3))
        assert accepted.applied == 1
        assert accepted.poisoned == 0
        assert second.poison_count() == 0
        assert SpineCursorRead(second, fence).read().poison_count == 0
        assert SpineQuarantine(second).card("tenant-a")["count"] == 0
    runtime.close()

def test_projection_keyset_scan_reaches_rows_beyond_batch_limit(
    tmp_path: Path,
) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "stream.sqlite")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    operation_ids = []
    for index in range(3):
        operation_id = f"11111111-1111-4111-8111-{index + 10:012d}"
        operation_ids.append(operation_id)
        operations.create(
            OperationEnvelope(
                operation_id=operation_id,
                tenant_id="tenant-scan",
                actor_id="actor-scan",
                capability="chat",
                created_at=BASE + timedelta(seconds=index),
                deadline=BASE + timedelta(minutes=5),
                idempotency_key=f"idem-scan-{index}",
                trace_id=f"trace-scan-{index}",
            ),
            now=BASE + timedelta(seconds=index),
        )
        runtime.dispatch_outbox(operation_id=operation_id)

    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(
        operations,
        inbox,
        fence,
        journal_path=tmp_path / "journal.sqlite",
    ) as projection:
        first = projection.project(limit=2)
        second = projection.project(limit=2)
        assert first.applied == 2
        assert second.applied == 1
        assert second.duplicates == 0
        assert SpineCursorRead(projection, fence).read().applied_count == 3

        third = projection.project(limit=2)
        assert third.duplicates == 2
        assert third.applied == 0
        assert SpineCursorRead(projection, fence).read().applied_count == 3
    runtime.close()
