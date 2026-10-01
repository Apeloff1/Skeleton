from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard, SpineDispatchGuardError
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_poison_apply import SpinePoisonApply
from skeleton.persistence.spine_poison_chain import SpinePoisonChain
from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket
from skeleton.persistence.spine_reaccept import SpineReaccept


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "34343434-3434-4343-8343-343434343434"
EVENT = "35353535-3535-4353-8353-353535353535"


def _delivery() -> InboxDelivery:
    return InboxDelivery(
        event_id=EVENT,
        operation_id=OP,
        operation_version=1,
        event_type="operation.created",
        payload={"n": 1},
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-chain",
    )


def test_chain_changes_when_journal_row_is_rewritten(tmp_path: Path) -> None:
    hold = SpineHold(tmp_path / "hold.sqlite")
    hold.hold(tenant_id="tenant-chain", outbox_id=EVENT, reason="poison", now=BASE)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    ticket = SpinePoisonTicket(tmp_path / "hold.sqlite", tmp_path / "ticket.sqlite")
    delivery = _delivery()
    issued = ticket.issue(tenant_id="tenant-chain", outbox_id=EVENT, digest=delivery.digest(), now=BASE)
    apply = SpinePoisonApply(
        tmp_path / "hold.sqlite",
        SpineReaccept(inbox, fence),
        ticket,
        tmp_path / "journal.sqlite",
    )
    card = apply.apply(
        delivery,
        tenant_id="tenant-chain",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    assert card["applied"] == 1
    assert card["epoch_before"] == card["epoch_after"] == 0
    chain = SpinePoisonChain(tmp_path / "journal.sqlite")
    sealed = chain.seal("tenant-chain")
    assert sealed["rows"] == 1
    assert sealed["applied_fence"] is False
    assert chain.verify("tenant-chain", sealed["chain"])["match"] is True
    import sqlite3

    connection = sqlite3.connect(tmp_path / "journal.sqlite")
    connection.execute("UPDATE spine_poison_apply SET applied = 0 WHERE tenant_id = ?", ("tenant-chain",))
    connection.commit()
    connection.close()
    assert chain.verify("tenant-chain", sealed["chain"])["match"] is False


class _Runtime:
    def start_dispatcher(self) -> None:
        raise AssertionError("guard must not call start_dispatcher")


def test_dispatch_guard_does_not_replace_or_call() -> None:
    runtime = _Runtime()
    guard = SpineDispatchGuard()
    before = guard.snapshot(runtime)
    after = guard.compare(before, runtime)
    assert after["same"] is True
    assert after["called"] is False
    assert after["runtime_replaced"] is False
    assert after["completion_checkbox"] is False
    runtime.start_dispatcher = lambda: None  # type: ignore[method-assign]
    try:
        guard.compare(before, runtime)
    except SpineDispatchGuardError as exc:
        assert "identity changed" in str(exc)
    else:
        raise AssertionError("changed identity must fail closed")
