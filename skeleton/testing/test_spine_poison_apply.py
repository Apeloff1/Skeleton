from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_gate import SpineGate
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_poison_apply import (
    SpinePoisonApply,
    SpinePoisonApplyError,
)
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
    assert card["hold_id"] == issued["hold_id"]
    assert card["hold_released"] is True
    assert card["released_hold_rows"] == 1
    assert inbox.applied_count() == 1

    post_ticket = ticket.issue(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        digest=delivery.digest(),
        now=BASE,
    )
    assert post_ticket["hit"] is False
    assert post_ticket["reason"] == "unheld"

    gate = SpineGate(
        tmp_path / "hold.sqlite",
        SpineReaccept(
            inbox,
            SQLiteConsistencyFence(tmp_path / "fence.sqlite"),
        ),
    )
    post_gate = gate.allow(
        delivery,
        tenant_id="tenant-poison",
        expected_digest=delivery.digest(),
        outbox_id=EVENT,
        now=BASE,
    )
    assert post_gate["reason"] == "duplicate"
    again = apply.apply(
        delivery,
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    assert again["reason"] == "ticket-consumed"
    assert again["applied"] == 0
    assert again["epoch_before"] == again["epoch_after"] == 0
    assert inbox.applied_count() == 1
    assert witness.card("tenant-poison")["applied"] == 1
    assert witness.card("tenant-other")["applied"] == 0


def test_ticket_is_bound_to_exact_hold_row_and_newer_hold_fails_closed(
    tmp_path: Path,
) -> None:
    hold, apply, witness, inbox = _stack(tmp_path)
    delivery = _delivery()
    first = hold.hold(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        reason="poison-first",
        now=BASE,
    )
    ticket = SpinePoisonTicket(
        tmp_path / "hold.sqlite",
        tmp_path / "ticket.sqlite",
    )
    issued = ticket.issue(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        digest=delivery.digest(),
        now=BASE,
    )
    assert issued["hold_id"] >= 1

    second = hold.hold(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        reason="poison-newer",
        now=BASE,
    )
    assert first["hit"] is True and second["hit"] is True

    refused = apply.apply(
        delivery,
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    assert refused["reason"] == "hold-drift"
    assert refused["applied"] == 0
    row = ticket.read(issued["ticket_id"])
    assert row is not None
    assert row["consumed"] == 0
    assert inbox.applied_count() == 0
    assert witness.card("tenant-poison")["applied"] == 0


def test_ticket_consume_is_one_time_and_idempotent(tmp_path: Path) -> None:
    hold = SpineHold(tmp_path / "hold.sqlite")
    delivery = _delivery()
    hold.hold(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        reason="poison",
        now=BASE,
    )
    ticket = SpinePoisonTicket(
        tmp_path / "hold.sqlite",
        tmp_path / "ticket.sqlite",
    )
    issued = ticket.issue(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        digest=delivery.digest(),
        now=BASE,
    )
    assert ticket.consume(issued["ticket_id"], now=BASE) is True
    assert ticket.consume(issued["ticket_id"], now=BASE) is False
    row = ticket.read(issued["ticket_id"])
    assert row is not None
    assert row["consumed"] == 1


def test_poison_digest_must_be_lowercase_sha256_hex(tmp_path: Path) -> None:
    hold, apply, _witness, _inbox = _stack(tmp_path)
    delivery = _delivery()
    hold.hold(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        reason="poison",
        now=BASE,
    )
    with pytest.raises(
        SpinePoisonApplyError,
        match="lowercase SHA-256 hex",
    ):
        apply.apply(
            delivery,
            tenant_id="tenant-poison",
            outbox_id=EVENT,
            expected_digest="g" * 64,
            ticket_id="invalid",
            now=BASE,
        )


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


def test_reaccept_exception_is_journaled_after_ticket_claim(
    tmp_path: Path,
) -> None:
    hold_path = tmp_path / "hold.sqlite"
    ticket_path = tmp_path / "ticket.sqlite"
    journal_path = tmp_path / "journal.sqlite"
    hold = SpineHold(hold_path)
    delivery = _delivery()
    hold.hold(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        reason="poison",
        now=BASE,
    )
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    reaccept = SpineReaccept(inbox, fence)
    ticket = SpinePoisonTicket(hold_path, ticket_path)
    issued = ticket.issue(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        digest=delivery.digest(),
        now=BASE,
    )
    apply = SpinePoisonApply(
        hold_path,
        reaccept,
        ticket,
        journal_path,
    )

    def _boom(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic reaccept fault")

    reaccept.reaccept = _boom  # type: ignore[method-assign]
    with pytest.raises(
        SpinePoisonApplyError,
        match="one-time ticket claim",
    ):
        apply.apply(
            delivery,
            tenant_id="tenant-poison",
            outbox_id=EVENT,
            expected_digest=delivery.digest(),
            ticket_id=issued["ticket_id"],
            now=BASE,
        )

    row = ticket.read(issued["ticket_id"])
    assert row is not None
    assert row["consumed"] == 1
    witness = SpinePoisonWitness(journal_path).card("tenant-poison")
    assert witness["seen"] == 1
    assert witness["applied"] == 0


def test_success_journal_has_unique_ticket_boundary(tmp_path: Path) -> None:
    hold, apply, _witness, _inbox = _stack(tmp_path)
    delivery = _delivery()
    hold.hold(
        tenant_id="tenant-poison",
        outbox_id=EVENT,
        reason="poison",
        now=BASE,
    )
    ticket = SpinePoisonTicket(
        tmp_path / "hold.sqlite",
        tmp_path / "ticket.sqlite",
    )
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

    import sqlite3

    connection = sqlite3.connect(tmp_path / "journal.sqlite")
    row = connection.execute(
        """
        SELECT tenant_id, outbox_id, digest, reason, epoch_before,
               epoch_after, applied, ticket_id, applied_at
        FROM spine_poison_apply
        WHERE ticket_id = ?
        """,
        (issued["ticket_id"],),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO spine_poison_apply(
                tenant_id, outbox_id, digest, reason, epoch_before,
                epoch_after, applied, ticket_id, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
    connection.close()


def test_apply_gate_still_refuses(tmp_path: Path) -> None:
    intent = RepairIntent("outbox", "tenant-poison", "poison", BASE)
    refusal = SpineApplyGate().consider(intent, now=BASE)
    assert refusal.as_dict()["applied"] == 0
    assert refusal.as_dict()["reason"] == "apply-not-landed"
