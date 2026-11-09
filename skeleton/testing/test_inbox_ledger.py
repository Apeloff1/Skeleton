from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.persistence.inbox_ledger import (
    InboxAcceptResult,
    InboxConflict,
    InboxDelivery,
    InboxLedgerError,
    SQLiteInboxLedger,
    delivery_from_outbox,
)
from skeleton.persistence.operation_store import OperationOutboxEvent


BASE = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def _delivery(
    *,
    version: int = 1,
    tenant: str = "tenant-a",
    payload: dict | None = None,
    event_id: str | None = None,
    operation_id: str | None = None,
    published_delta: timedelta = timedelta(seconds=1),
) -> InboxDelivery:
    created = BASE
    return InboxDelivery(
        event_id=event_id or str(uuid4()),
        operation_id=operation_id or str(uuid4()),
        operation_version=version,
        event_type="operation.created",
        payload=payload or {"state": "created", "version": version},
        created_at=created,
        published_at=created + published_delta,
        tenant_id=tenant,
    )


def test_accept_advances_watermark_and_replays_same_digest() -> None:
    delivery = _delivery()
    with SQLiteInboxLedger() as ledger:
        first = ledger.accept(delivery, consumer_id="worker-a", now=BASE + timedelta(seconds=2))
        assert first.duplicate is False
        assert first.applied_through == 1
        again = ledger.accept(delivery, consumer_id="worker-a", now=BASE + timedelta(seconds=3))
        assert again.duplicate is True
        assert again.applied_through == 1
        assert ledger.applied_count("worker-a") == 1
        card = ledger.card()
        assert card["stored_prose"] == 0
        assert card["completion_checkbox"] is False
        assert card["citation"] == "VOL-134"


def test_digest_drift_and_gap_and_unpublished_are_conflicts() -> None:
    operation_id = str(uuid4())
    first = _delivery(version=1, operation_id=operation_id)
    drifted = _delivery(
        version=1,
        operation_id=operation_id,
        event_id=first.event_id,
        payload={"state": "created", "version": 1, "mutated": True},
    )
    gap = _delivery(version=3, operation_id=operation_id)
    with SQLiteInboxLedger() as ledger:
        ledger.accept(first, consumer_id="worker-a", now=BASE + timedelta(seconds=2))
        with pytest.raises(InboxConflict, match="different content"):
            ledger.accept(drifted, consumer_id="worker-a", now=BASE + timedelta(seconds=3))
        with pytest.raises(InboxConflict, match="contiguous"):
            ledger.accept(gap, consumer_id="worker-a", now=BASE + timedelta(seconds=3))

    unpublished = OperationOutboxEvent(
        outbox_id=str(uuid4()),
        operation_id=operation_id,
        operation_version=1,
        event_type="operation.created",
        payload={"state": "created"},
        created_at=BASE,
        published_at=None,
    )
    with pytest.raises(InboxConflict, match="unpublished"):
        delivery_from_outbox(unpublished, "tenant-a")


def test_tenant_fence_and_publication_order() -> None:
    operation_id = str(uuid4())
    first = _delivery(version=1, operation_id=operation_id, tenant="tenant-a")
    other = _delivery(version=2, operation_id=operation_id, tenant="tenant-b")
    early = _delivery(published_delta=timedelta(seconds=-1))
    with SQLiteInboxLedger() as ledger:
        ledger.accept(first, consumer_id="worker-a", now=BASE + timedelta(seconds=2))
        with pytest.raises(InboxConflict, match="another tenant"):
            ledger.accept(other, consumer_id="worker-a", now=BASE + timedelta(seconds=3))
        with pytest.raises(InboxConflict, match="predate event creation"):
            ledger.accept(early, consumer_id="worker-a", now=BASE + timedelta(seconds=2))
        with pytest.raises(InboxLedgerError, match="unknown inbox receipt"):
            ledger.get("worker-a", str(uuid4()))


def test_published_outbox_adapter_round_trip() -> None:
    event = OperationOutboxEvent(
        outbox_id=str(uuid4()),
        operation_id=str(uuid4()),
        operation_version=1,
        event_type="operation.created",
        payload={"state": "created", "version": 1},
        created_at=BASE,
        published_at=BASE + timedelta(seconds=1),
    )
    delivery = delivery_from_outbox(event, "tenant-a")
    with SQLiteInboxLedger() as ledger:
        result = ledger.accept(delivery, consumer_id="inbox-1", now=BASE + timedelta(seconds=2))
        assert isinstance(result, InboxAcceptResult)
        assert result.receipt.payload_digest
        assert ledger.applied_through("inbox-1", event.operation_id) == 1


def test_rejects_noncanonical_identity() -> None:
    delivery = _delivery()
    with SQLiteInboxLedger() as ledger:
        with pytest.raises(InboxLedgerError):
            ledger.accept(delivery, consumer_id=" worker-a")
        with pytest.raises(InboxLedgerError):
            SQLiteInboxLedger(namespace=" inbox")
