from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_hold_agree import SpineBindHoldAgree, SpineBindHoldAgreeError
from skeleton.persistence.spine_bind_hold_agree_chain import SpineBindHoldAgreeChain, SpineBindHoldAgreeChainError
from skeleton.persistence.spine_bind_hold_agree_journal import (
    SpineBindHoldAgreeJournal,
    SpineBindHoldAgreeJournalError,
)
from skeleton.persistence.spine_bind_hold_agree_read import SpineBindHoldAgreeRead, SpineBindHoldAgreeReadError


def _parts() -> tuple[dict, dict, dict]:
    release = {
        "kind": "spine_bind_hold_release",
        "tenant_id": "house-a",
        "outbox_id": "ob-1",
        "hold_id": 3,
        "released": False,
        "applied": 0,
        "epoch_before": 4,
        "epoch_after": 4,
    }
    ticket = {
        "kind": "spine_bind_hold_ticket",
        "tenant_id": "house-a",
        "outbox_id": "ob-1",
        "tickets": 1,
        "consumed": 0,
        "applied": 0,
    }
    fence = {
        "kind": "spine_bind_hold_fence",
        "tenant_id": "house-a",
        "outbox_id": "ob-1",
        "epoch_before": 4,
        "epoch_after": 4,
        "moved": False,
        "applied": 0,
    }
    return release, ticket, fence


def test_agree_refuses_a_mismatch_and_journal_hides_foreign(tmp_path: Path) -> None:
    release, ticket, fence = _parts()
    card = SpineBindHoldAgree().card(release=release, ticket=ticket, fence=fence)
    assert card["released"] is False
    assert card["consumed"] == 0
    assert card["moved"] is False
    assert card["hit"] is False
    foreign = dict(ticket)
    foreign["tenant_id"] = "house-b"
    with pytest.raises(SpineBindHoldAgreeError):
        SpineBindHoldAgree().card(release=release, ticket=foreign, fence=fence)
    path = tmp_path / "agree.sqlite"
    journal = SpineBindHoldAgreeJournal(path)
    sealed = journal.append(card)
    again = journal.append(card)
    assert sealed["rewritten"] is False
    assert again["digest"] == sealed["digest"]
    journal.close()
    reader = SpineBindHoldAgreeRead(path)
    assert reader.card("house-a", "ob-1")["seen"] is True
    assert reader.card("house-b", "ob-1")["seen"] is False
    reader.close()
    with pytest.raises(SpineBindHoldAgreeJournalError):
        SpineBindHoldAgreeJournal(path).append({**card, "hold_id": 9})


def test_read_and_chain_refuse_a_lit_row(tmp_path: Path) -> None:
    release, ticket, fence = _parts()
    card = SpineBindHoldAgree().card(release=release, ticket=ticket, fence=fence)
    path = tmp_path / "agree.sqlite"
    SpineBindHoldAgreeJournal(path).append(card)
    chain = SpineBindHoldAgreeChain(path)
    sealed = chain.seal("house-a")
    assert sealed["rows"] == 1
    assert sealed["consumed"] == 0
    assert len(sealed["digest"]) == 64
    chain.close()
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute("UPDATE spine_bind_hold_agree SET consumed = 1 WHERE tenant_id = ?", ("house-a",))
    conn.commit()
    conn.close()
    with pytest.raises(SpineBindHoldAgreeReadError):
        SpineBindHoldAgreeRead(path).card("house-a", "ob-1")
    with pytest.raises(SpineBindHoldAgreeChainError):
        SpineBindHoldAgreeChain(path).seal("house-a")
