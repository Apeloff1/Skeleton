from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.inbox_ledger import InboxConflict, InboxDelivery
from skeleton.persistence.mongo_inbox import MongoInboxLedger


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "77777777-7777-4777-8777-777777777777"


def _delivery(version: int, event_id: str, payload: dict[str, int]) -> InboxDelivery:
    return InboxDelivery(
        event_id=event_id,
        operation_id=OP,
        operation_version=version,
        event_type="operation.created",
        payload=payload,
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-mongo",
    )


def test_mongo_inbox_accepts_once_and_rejects_gap() -> None:
    inbox = MongoInboxLedger(None)
    first = inbox.accept(
        _delivery(1, "88888888-8888-4888-8888-888888888888", {"n": 1}),
        consumer_id="mongo",
        now=BASE,
    )
    assert first.duplicate is False
    assert first.applied_through == 1
    again = inbox.accept(
        _delivery(1, "88888888-8888-4888-8888-888888888888", {"n": 1}),
        consumer_id="mongo",
        now=BASE,
    )
    assert again.duplicate is True
    with pytest.raises(InboxConflict):
        inbox.accept(
            _delivery(3, "99999999-9999-4999-8999-999999999999", {"n": 3}),
            consumer_id="mongo",
            now=BASE,
        )
    card = inbox.card()
    assert card["stored_prose"] == 0
    assert card["completion_checkbox"] is False


def test_mongo_inbox_rejects_digest_conflict() -> None:
    inbox = MongoInboxLedger(None)
    inbox.accept(
        _delivery(1, "88888888-8888-4888-8888-888888888888", {"n": 1}),
        consumer_id="mongo",
        now=BASE + timedelta(seconds=1),
    )
    with pytest.raises(InboxConflict):
        inbox.accept(
            _delivery(1, "88888888-8888-4888-8888-888888888888", {"n": 2}),
            consumer_id="mongo",
            now=BASE + timedelta(seconds=1),
        )
