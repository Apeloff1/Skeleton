from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_replay import SpineReplay


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "19191919-1919-4919-8919-191919191919"
EVENT = "20202020-2020-4020-8020-202020202020"


def _delivery(payload: dict[str, int]) -> InboxDelivery:
    return InboxDelivery(
        event_id=EVENT,
        operation_id=OP,
        operation_version=1,
        event_type="operation.created",
        payload=payload,
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-replay",
    )


def test_replay_of_duplicate_does_not_move_fence(tmp_path: Path) -> None:
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    delivery = _delivery({"n": 1})
    inbox.accept(delivery, consumer_id="spine", now=BASE)
    card = SpineReplay(inbox, fence).replay(delivery, tenant_id="tenant-replay", now=BASE)
    assert card["duplicate"] is True
    assert card["epoch_before"] == 0
    assert card["epoch_after"] == 0
    assert card["completion_checkbox"] is False


def test_replay_refuses_digest_change(tmp_path: Path) -> None:
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    inbox.accept(_delivery({"n": 1}), consumer_id="spine", now=BASE)
    card = SpineReplay(inbox, fence).replay(_delivery({"n": 2}), tenant_id="tenant-replay", now=BASE)
    assert card["duplicate"] is False
    assert card["reason"] == "InboxConflict"
    assert card["epoch_after"] == 0
