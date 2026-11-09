from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_reaccept import SpineReaccept


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "22222222-2222-4222-8222-222222222222"
EVENT = "23232323-2323-4232-8232-232323232323"


def _delivery() -> InboxDelivery:
    return InboxDelivery(
        event_id=EVENT,
        operation_id=OP,
        operation_version=1,
        event_type="operation.created",
        payload={"n": 1},
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-reaccept",
    )


def test_mismatch_is_refused_before_accept(tmp_path: Path) -> None:
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    card = SpineReaccept(inbox, fence).reaccept(
        _delivery(),
        tenant_id="tenant-reaccept",
        expected_digest="0" * 64,
        now=BASE,
    )
    assert card["reason"] == "digest-mismatch"
    assert card["applied_fence"] is False
    assert card["completion_checkbox"] is False


def test_duplicate_reaccept_does_not_move_fence(tmp_path: Path) -> None:
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    delivery = _delivery()
    inbox.accept(delivery, consumer_id="spine", now=BASE)
    card = SpineReaccept(inbox, fence).reaccept(
        delivery,
        tenant_id="tenant-reaccept",
        expected_digest=delivery.digest(),
        now=BASE,
    )
    assert card["duplicate"] is True
    assert card["epoch_before"] == card["epoch_after"] == 0
