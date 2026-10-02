from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_hold import SpineBindHold
from skeleton.persistence.spine_bind_hold_fence import SpineBindHoldFence, SpineBindHoldFenceError
from skeleton.persistence.spine_bind_hold_release import SpineBindHoldRelease, SpineBindHoldReleaseError
from skeleton.persistence.spine_bind_hold_release_journal import (
    SpineBindHoldReleaseJournal,
    SpineBindHoldReleaseJournalError,
)
from skeleton.persistence.spine_bind_hold_ticket import SpineBindHoldTicket, SpineBindHoldTicketError
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket


def _bind() -> dict:
    return {
        "kind": "spine_bind_card",
        "tenant_id": "house-a",
        "apply_landed": False,
        "moved": False,
        "digest": "ab" * 32,
    }


def _refusal(tmp_path: Path) -> tuple[Path, dict]:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(tenant_id="house-a", outbox_id="ob-1", reason="poison", now=datetime.now(timezone.utc))
    hold.close()
    card = SpineBindHold(path).refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=4,
        epoch_after=4,
    )
    return path, card


def test_refusal_does_not_release_and_rewrite_fails(tmp_path: Path) -> None:
    path, card = _refusal(tmp_path)
    proof = SpineBindHoldRelease(path).prove(card)
    assert proof["released"] is False
    assert proof["applied"] == 0
    assert proof["hold_id"] == card["hold_id"]
    journal = SpineBindHoldReleaseJournal(tmp_path / "release.sqlite")
    sealed = journal.append(proof)
    again = journal.append(proof)
    assert sealed["rewritten"] is False
    assert again["digest"] == sealed["digest"]
    journal.close()
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute("UPDATE spine_hold SET released = 1 WHERE hold_id = ?", (card["hold_id"],))
    conn.commit()
    conn.close()
    with pytest.raises(SpineBindHoldReleaseError):
        SpineBindHoldRelease(path).prove(card)
    with pytest.raises(SpineBindHoldReleaseJournalError):
        SpineBindHoldReleaseJournal(tmp_path / "release.sqlite").append({**proof, "hold_id": proof["hold_id"] + 1})


def test_refusal_does_not_consume_a_ticket(tmp_path: Path) -> None:
    path, card = _refusal(tmp_path)
    tickets = tmp_path / "tickets.sqlite"
    SpinePoisonTicket(path, tickets).issue(
        tenant_id="house-a",
        outbox_id="ob-1",
        digest="cd" * 32,
        now=datetime.now(timezone.utc),
    )
    proof = SpineBindHoldTicket(tickets).prove(card)
    assert proof["tickets"] == 1
    assert proof["consumed"] == 0
    import sqlite3

    conn = sqlite3.connect(tickets)
    conn.execute("UPDATE spine_poison_ticket SET consumed = 1 WHERE outbox_id = ?", ("ob-1",))
    conn.commit()
    conn.close()
    with pytest.raises(SpineBindHoldTicketError):
        SpineBindHoldTicket(tickets).prove(card)


def test_fence_probe_matches_refusal_and_refuses_a_move() -> None:
    refusal = {
        "kind": "spine_bind_hold",
        "tenant_id": "house-a",
        "outbox_id": "ob-1",
        "epoch_before": 6,
        "epoch_after": 6,
        "moved": False,
        "applied": 0,
    }
    card = SpineBindHoldFence().card(refusal, epoch_before=6, epoch_after=6)
    assert card["moved"] is False
    assert card["applied"] == 0
    with pytest.raises(SpineBindHoldFenceError):
        SpineBindHoldFence().card(refusal, epoch_before=6, epoch_after=7)
