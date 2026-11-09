from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_gate import SpineGate
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_reaccept import SpineReaccept
from skeleton.persistence.spine_watch import SpineWatch


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "24242424-2424-4242-8242-242424242424"
EVENT = "25252525-2525-4252-8252-252525252525"
OUTBOX = "26262626-2626-4262-8262-262626262626"


def _delivery() -> InboxDelivery:
    return InboxDelivery(
        event_id=EVENT,
        operation_id=OP,
        operation_version=1,
        event_type="operation.created",
        payload={"n": 1},
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-gate",
    )


def test_held_id_is_refused_and_watch_sees_no_move(tmp_path: Path) -> None:
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    hold_path = tmp_path / "hold.sqlite"
    hold = SpineHold(hold_path)
    hold.hold(tenant_id="tenant-gate", outbox_id=OUTBOX, reason="apply-not-landed", now=BASE)
    hold.close()
    reaccept = SpineReaccept(inbox, fence)
    delivery = _delivery()
    gate = SpineGate(hold_path, reaccept)
    refused = gate.allow(
        delivery,
        tenant_id="tenant-gate",
        expected_digest=delivery.digest(),
        outbox_id=OUTBOX,
        now=BASE,
    )
    assert refused["reason"] == "held"
    assert refused["applied_fence"] is False
    watched = SpineWatch(reaccept).watch(
        delivery,
        tenant_id="tenant-gate",
        expected_digest=delivery.digest(),
        now=BASE,
    )
    assert watched["moved"] is False
    assert watched["epoch_before"] == watched["epoch_after"]
    gate.close()
