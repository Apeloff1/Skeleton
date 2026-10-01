from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_hold import SpineBindHold, SpineBindHoldError
from skeleton.persistence.spine_bind_hold_chain import SpineBindHoldChain, SpineBindHoldChainError
from skeleton.persistence.spine_bind_hold_journal import SpineBindHoldJournal, SpineBindHoldJournalError
from skeleton.persistence.spine_bind_hold_read import SpineBindHoldRead, SpineBindHoldReadError
from skeleton.persistence.spine_hold import SpineHold


def _bind(tenant: str = "house-a") -> dict:
    return {
        "kind": "spine_bind_card",
        "tenant_id": tenant,
        "apply_landed": False,
        "moved": False,
        "digest": "c" * 64,
    }


def test_held_id_refuses_seal_and_foreign_hold_does_not(tmp_path: Path) -> None:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(tenant_id="house-a", outbox_id="ob-1", reason="poison", now=datetime.now(timezone.utc))
    hold.hold(tenant_id="house-b", outbox_id="ob-9", reason="other", now=datetime.now(timezone.utc))
    hold.close()
    gate = SpineBindHold(path)
    refused = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=4,
        epoch_after=4,
    )
    assert refused["held"] is True
    assert refused["sealed"] is False
    assert refused["applied"] == 0
    assert refused["moved"] is False
    open_row = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-9",
        bind=_bind(),
        epoch_before=4,
        epoch_after=4,
    )
    assert open_row["held"] is False
    assert open_row["sealed"] is False
    with pytest.raises(SpineBindHoldError):
        gate.refuse(
            tenant_id="house-a",
            outbox_id="ob-1",
            bind=_bind(),
            epoch_before=4,
            epoch_after=5,
        )
    gate.close()


def test_journal_refuses_a_rewrite_and_read_hides_foreign(tmp_path: Path) -> None:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(tenant_id="house-a", outbox_id="ob-1", reason="poison", now=datetime.now(timezone.utc))
    hold.close()
    gate = SpineBindHold(path)
    card = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=2,
        epoch_after=2,
    )
    gate.close()
    journal_path = tmp_path / "refusal.sqlite"
    journal = SpineBindHoldJournal(journal_path)
    sealed = journal.append(card)
    again = journal.append(card)
    assert sealed["rewritten"] is False
    assert again["digest"] == sealed["digest"]
    assert again["applied"] == 0
    journal.close()
    reader = SpineBindHoldRead(journal_path)
    seen = reader.card("house-a", "ob-1")
    assert seen["seen"] is True
    assert seen["applied"] == 0
    assert reader.card("house-b", "ob-1")["seen"] is False
    reader.close()
    import sqlite3

    conn = sqlite3.connect(journal_path)
    conn.execute("UPDATE spine_bind_hold SET applied = 1 WHERE tenant_id = ?", ("house-a",))
    conn.commit()
    conn.close()
    reader = SpineBindHoldRead(journal_path)
    with pytest.raises(SpineBindHoldReadError):
        reader.card("house-a", "ob-1")
    reader.close()
    with pytest.raises(SpineBindHoldJournalError):
        SpineBindHoldJournal(journal_path).append({**card, "reason": "other"})


def test_chain_refuses_a_rewritten_row(tmp_path: Path) -> None:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(tenant_id="house-a", outbox_id="ob-1", reason="poison", now=datetime.now(timezone.utc))
    hold.close()
    card = SpineBindHold(path).refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=1,
        epoch_after=1,
    )
    journal_path = tmp_path / "refusal.sqlite"
    SpineBindHoldJournal(journal_path).append(card)
    chain = SpineBindHoldChain(journal_path)
    sealed = chain.seal("house-a")
    assert sealed["rows"] == 1
    assert sealed["applied"] == 0
    assert len(sealed["digest"]) == 64
    chain.close()
    import sqlite3

    conn = sqlite3.connect(journal_path)
    conn.execute("UPDATE spine_bind_hold SET applied = 1 WHERE tenant_id = ?", ("house-a",))
    conn.commit()
    conn.close()
    with pytest.raises(SpineBindHoldChainError):
        SpineBindHoldChain(journal_path).seal("house-a")
