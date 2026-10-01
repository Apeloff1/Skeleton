from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_poison_apply import SpinePoisonApply
from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket
from skeleton.persistence.spine_poison_witness import SpinePoisonWitness
from skeleton.persistence.spine_reaccept import SpineReaccept
from skeleton.persistence.spine_repair import RepairIntent


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "24242424-2424-4242-8242-242424242424"
EVENT = "25252525-2525-4252-8252-252525252525"


def _delivery(tenant: str = "tenant-poison") -> InboxDelivery:
    return InboxDelivery(
        event_id=EVENT,
        operation_id=OP,
        operation_version=1,
        event_type="operation.created",
        payload={"n": 1},
        created_at=BASE,
        published_at=BASE,
        tenant_id=tenant,
    )


def _stack(tmp_path: Path) -> tuple[SpineHold, SpinePoisonApply, SpinePoisonWitness, SQLiteInboxLedger]:
    hold = SpineHold(tmp_path / "hold.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    ticket = SpinePoisonTicket(tmp_path / "hold.sqlite", tmp_path / "ticket.sqlite")
    apply = SpinePoisonApply(
        tmp_path / "hold.sqlite",
        SpineReaccept(inbox, fence),
        ticket,
        tmp_path / "journal.sqlite",
    )
    witness = SpinePoisonWitness(tmp_path / "journal.sqlite")
    return hold, apply, witness, inbox


def test_unheld_id_is_not_applied(tmp_path: Path) -> None:
    _hold, apply, witness, inbox = _stack(tmp_path)
    delivery = _delivery()
    card = apply.apply(
        delivery,
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id="missing-ticket",
        now=BASE,
    )
    assert card["reason"] == "unheld"
    assert card["applied"] == 0
    assert card["applied_fence"] is False
    assert card["completion_checkbox"] is False
    assert inbox.applied_count() == 0
    assert witness.card("tenant-poison")["applied"] == 0


def test_digest_mismatch_is_conflict_before_accept(tmp_path: Path) -> None:
    hold, apply, _witness, inbox = _stack(tmp_path)
    hold.hold(tenant_id="tenant-poison", outbox_id=EVENT, reason="poison", now=BASE)
    ticket = SpinePoisonTicket(tmp_path / "hold.sqlite", tmp_path / "ticket.sqlite")
    issued = ticket.issue(tenant_id="tenant-poison", outbox_id=EVENT, digest="ab" * 32, now=BASE)
    card = apply.apply(
        _delivery(),
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        expected_digest="ab" * 32,
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    assert card["reason"] == "digest-mismatch"
    assert card["applied"] == 0
    assert card["epoch_before"] == card["epoch_after"] == 0
    assert inbox.applied_count() == 0


def test_matching_digest_applies_without_moving_fence(tmp_path: Path) -> None:
    hold, apply, witness, inbox = _stack(tmp_path)
    delivery = _delivery()
    hold.hold(tenant_id="tenant-poison", outbox_id=EVENT, reason="poison", now=BASE)
    ticket = SpinePoisonTicket(tmp_path / "hold.sqlite", tmp_path / "ticket.sqlite")
    issued = ticket.issue(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        digest=delivery.digest(),
        now=BASE,
    )
    card = apply.apply(
        delivery,
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    assert card["applied"] == 1
    assert card["reason"] == "accepted"
    assert card["epoch_before"] == card["epoch_after"] == 0
    assert card["applied_fence"] is False
    assert inbox.applied_count() == 1
    again = apply.apply(
        delivery,
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    assert again["reason"] == "duplicate"
    assert again["epoch_before"] == again["epoch_after"] == 0
    assert inbox.applied_count() == 1
    assert witness.card("tenant-poison")["applied"] == 2
    assert witness.card("tenant-other")["applied"] == 0


def test_foreign_tenant_cannot_apply_held_id(tmp_path: Path) -> None:
    hold, apply, _witness, inbox = _stack(tmp_path)
    hold.hold(tenant_id="tenant-poison", outbox_id=EVENT, reason="poison", now=BASE)
    card = apply.apply(
        _delivery("tenant-other"),
        tenant_id="tenant-other",
        outbox_id=EVENT,
        expected_digest=_delivery().digest(),
        ticket_id="foreign",
        now=BASE,
    )
    assert card["reason"] == "unheld"
    assert card["applied"] == 0
    assert inbox.applied_count() == 0


def test_apply_gate_still_refuses(tmp_path: Path) -> None:
    intent = RepairIntent("outbox", "tenant-poison", "poison", BASE)
    refusal = SpineApplyGate().consider(intent, now=BASE)
    assert refusal.as_dict()["applied"] == 0
    assert refusal.as_dict()["reason"] == "apply-not-landed"
