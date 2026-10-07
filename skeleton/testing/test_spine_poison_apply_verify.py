from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxDelivery, SQLiteInboxLedger
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_poison_apply import SpinePoisonApply
from skeleton.persistence.spine_poison_apply_verify import (
    SpinePoisonApplyVerify,
    SpinePoisonApplyVerifyError,
)
from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket
from skeleton.persistence.spine_reaccept import SpineReaccept


BASE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
OP = "94949494-9494-4494-8494-949494949494"
EVENT = "95959595-9595-4595-8595-959595959595"


def _delivery() -> InboxDelivery:
    return InboxDelivery(
        event_id=EVENT,
        operation_id=OP,
        operation_version=1,
        event_type="operation.created",
        payload={"n": 1},
        created_at=BASE,
        published_at=BASE,
        tenant_id="tenant-poison-verify",
    )


def _applied(tmp_path: Path) -> tuple[dict[str, object], SpinePoisonApplyVerify]:
    hold_path = tmp_path / "hold.sqlite"
    ticket_path = tmp_path / "ticket.sqlite"
    journal_path = tmp_path / "journal.sqlite"
    hold = SpineHold(hold_path)
    hold.hold(tenant_id="tenant-poison-verify", outbox_id=EVENT, reason="poison", now=BASE)
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    ticket = SpinePoisonTicket(hold_path, ticket_path)
    delivery = _delivery()
    issued = ticket.issue(
        tenant_id="tenant-poison-verify",
        outbox_id=EVENT,
        digest=delivery.digest(),
        now=BASE,
    )
    apply = SpinePoisonApply(
        hold_path,
        SpineReaccept(inbox, fence),
        ticket,
        journal_path,
    )
    card = apply.apply(
        delivery,
        tenant_id="tenant-poison-verify",
        outbox_id=EVENT,
        expected_digest=delivery.digest(),
        ticket_id=issued["ticket_id"],
        now=BASE,
    )
    return card, SpinePoisonApplyVerify(journal_path, ticket)


def test_successful_poison_apply_reconciles_durable_evidence(tmp_path: Path) -> None:
    card, verify = _applied(tmp_path)
    result = verify.verify(card)
    assert result["verified"] is True
    assert result["journal_rows"] == 1
    assert result["ticket_consumed"] is True
    assert result["hold_id"] == card["hold_id"]
    assert result["hold_released"] is True
    assert result["released_hold_rows"] == 1
    assert result["epoch_before"] == result["epoch_after"] == 0
    assert result["apply_authority"] is False


def test_verifier_rejects_card_epoch_tamper(tmp_path: Path) -> None:
    card, verify = _applied(tmp_path)
    tampered = copy.deepcopy(card)
    tampered["epoch_after"] = 1
    with pytest.raises(SpinePoisonApplyVerifyError, match="moved the fence"):
        verify.verify(tampered)


def test_verifier_rejects_hold_identity_tamper(tmp_path: Path) -> None:
    card, verify = _applied(tmp_path)
    tampered = copy.deepcopy(card)
    tampered["hold_id"] += 1
    with pytest.raises(
        SpinePoisonApplyVerifyError,
        match="journal evidence mismatch",
    ):
        verify.verify(tampered)


def test_verifier_rejects_hold_release_tamper(tmp_path: Path) -> None:
    card, verify = _applied(tmp_path)
    tampered = copy.deepcopy(card)
    tampered["hold_released"] = False
    with pytest.raises(
        SpinePoisonApplyVerifyError,
        match="did not prove hold release",
    ):
        verify.verify(tampered)


def test_verifier_rejects_signoff_tamper(tmp_path: Path) -> None:
    card, verify = _applied(tmp_path)
    tampered = copy.deepcopy(card)
    tampered["completion_checkbox"] = True
    with pytest.raises(
        SpinePoisonApplyVerifyError,
        match="overclaimed authority",
    ):
        verify.verify(tampered)


def test_verifier_rejects_rewritten_journal_row(tmp_path: Path) -> None:
    card, verify = _applied(tmp_path)
    connection = sqlite3.connect(tmp_path / "journal.sqlite")
    connection.execute(
        "UPDATE spine_poison_apply SET reason = ? WHERE ticket_id = ?",
        ("rewritten", card["ticket_id"]),
    )
    connection.commit()
    connection.close()
    with pytest.raises(SpinePoisonApplyVerifyError, match="journal evidence mismatch"):
        verify.verify(card)
