from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from skeleton.persistence.spine_bind_hold import (
    SpineBindHold,
    SpineBindHoldError,
)
from skeleton.persistence.spine_bind_hold_chain import (
    SpineBindHoldChain,
    SpineBindHoldChainError,
)
from skeleton.persistence.spine_bind_hold_journal import (
    SpineBindHoldJournal,
    SpineBindHoldJournalError,
)
from skeleton.persistence.spine_bind_hold_read import (
    SpineBindHoldRead,
    SpineBindHoldReadError,
)
from skeleton.persistence.spine_bind_hold_verify import SpineBindHoldVerify
from skeleton.persistence.spine_hold import SpineHold


NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)


def _bind(tenant: str = "house-a") -> dict[str, object]:
    return {
        "kind": "spine_bind_card",
        "tenant_id": tenant,
        "apply_landed": False,
        "moved": False,
        "digest": "c" * 64,
    }


def _refusal(tmp_path: Path) -> tuple[dict[str, object], Path]:
    hold_path = tmp_path / "hold.sqlite"
    hold = SpineHold(hold_path)
    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="poison",
        now=NOW,
    )
    hold.close()
    gate = SpineBindHold(hold_path)
    card = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=2,
        epoch_after=2,
    )
    gate.close()
    return card, hold_path


def test_held_id_refuses_seal_and_foreign_hold_does_not(
    tmp_path: Path,
) -> None:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="poison",
        now=NOW,
    )
    hold.hold(
        tenant_id="house-b",
        outbox_id="ob-9",
        reason="other",
        now=NOW,
    )
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
    assert refused["bind_digest"] == "c" * 64
    open_row = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-9",
        bind=_bind(),
        epoch_before=4,
        epoch_after=4,
    )
    assert open_row["held"] is False
    assert open_row["sealed"] is False
    with pytest.raises(SpineBindHoldError, match="moved"):
        gate.refuse(
            tenant_id="house-a",
            outbox_id="ob-1",
            bind=_bind(),
            epoch_before=4,
            epoch_after=5,
        )
    with pytest.raises(SpineBindHoldError, match="lowercase SHA-256"):
        gate.refuse(
            tenant_id="house-a",
            outbox_id="ob-1",
            bind={**_bind(), "digest": "g" * 64},
            epoch_before=4,
            epoch_after=4,
        )
    gate.close()


def test_released_hold_no_longer_blocks_bind(tmp_path: Path) -> None:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="poison",
        now=NOW,
    )
    hold.close()

    connection = sqlite3.connect(path)
    connection.execute(
        """
        UPDATE spine_hold
        SET released = 1,
            released_at = ?,
            release_ticket_id = ?
        WHERE tenant_id = ? AND outbox_id = ?
        """,
        (NOW.isoformat(), "ticket-1", "house-a", "ob-1"),
    )
    connection.commit()
    connection.close()

    gate = SpineBindHold(path)
    card = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=3,
        epoch_after=3,
    )
    assert card["held"] is False
    assert card["hold_id"] is None
    assert card["reason"] is None
    gate.close()


def test_latest_active_hold_identity_is_bound(tmp_path: Path) -> None:
    path = tmp_path / "hold.sqlite"
    hold = SpineHold(path)
    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="older",
        now=NOW,
    )
    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="newer",
        now=NOW,
    )
    hold.close()

    gate = SpineBindHold(path)
    card = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=1,
        epoch_after=1,
    )
    assert card["held"] is True
    assert card["reason"] == "newer"
    assert card["hold_id"] == 2
    gate.close()


def test_journal_refuses_rewrite_and_read_reconstructs_digest(
    tmp_path: Path,
) -> None:
    card, _hold_path = _refusal(tmp_path)
    journal_path = tmp_path / "refusal.sqlite"
    journal = SpineBindHoldJournal(journal_path)
    sealed = journal.append(card)
    again = journal.append(card)
    assert sealed["rewritten"] is False
    assert again["digest"] == sealed["digest"]
    assert again["identity_digest"] == sealed["identity_digest"]
    assert len(sealed["identity_digest"]) == 64
    assert again["refusal_id"] == sealed["refusal_id"]
    assert again["hold_id"] == card["hold_id"]
    assert again["bind_digest"] == card["bind_digest"]
    assert again["applied"] == 0
    journal.close()

    reader = SpineBindHoldRead(journal_path)
    seen = reader.card("house-a", "ob-1")
    assert seen["seen"] is True
    assert seen["digest"] == sealed["digest"]
    assert seen["identity_digest"] == sealed["identity_digest"]
    assert seen["refusal_id"] == sealed["refusal_id"]
    assert seen["hold_id"] == card["hold_id"]
    assert seen["hold_reason"] == "poison"
    assert seen["bind_digest"] == "c" * 64
    assert seen["applied"] == 0
    assert reader.card("house-b", "ob-1")["seen"] is False
    reader.close()

    with pytest.raises(SpineBindHoldJournalError, match="rewrite"):
        SpineBindHoldJournal(journal_path).append(
            {**card, "reason": "other"}
        )


def test_later_hold_on_same_outbox_appends_new_refusal(
    tmp_path: Path,
) -> None:
    hold_path = tmp_path / "hold.sqlite"
    journal_path = tmp_path / "refusal.sqlite"
    hold = SpineHold(hold_path)
    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="first",
        now=NOW,
    )
    gate = SpineBindHold(hold_path)
    first = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=2,
        epoch_after=2,
    )
    journal = SpineBindHoldJournal(journal_path)
    first_sealed = journal.append(first)

    connection = sqlite3.connect(hold_path)
    connection.execute(
        """
        UPDATE spine_hold
        SET released = 1,
            released_at = ?,
            release_ticket_id = ?
        WHERE hold_id = ?
        """,
        (NOW.isoformat(), "ticket-first", first["hold_id"]),
    )
    connection.commit()
    connection.close()

    hold.hold(
        tenant_id="house-a",
        outbox_id="ob-1",
        reason="second",
        now=NOW,
    )
    second = gate.refuse(
        tenant_id="house-a",
        outbox_id="ob-1",
        bind=_bind(),
        epoch_before=2,
        epoch_after=2,
    )
    second_sealed = journal.append(second)
    assert second["hold_id"] != first["hold_id"]
    assert second_sealed["refusal_id"] > first_sealed["refusal_id"]

    reader = SpineBindHoldRead(journal_path)
    latest = reader.card("house-a", "ob-1")
    assert latest["refusal_id"] == second_sealed["refusal_id"]
    assert latest["hold_id"] == second["hold_id"]
    assert latest["hold_reason"] == "second"

    chain = SpineBindHoldChain(journal_path)
    sealed_chain = chain.seal("house-a")
    assert sealed_chain["rows"] == 2
    assert chain.verify("house-a", sealed_chain["digest"])["match"] is True

    verifier = SpineBindHoldVerify(journal_path)
    assert verifier.verify(first)["refusal_id"] == first_sealed["refusal_id"]
    assert verifier.verify(second)["refusal_id"] == second_sealed["refusal_id"]
    verifier.close()
    chain.close()
    reader.close()
    journal.close()
    gate.close()
    hold.close()


def test_read_rejects_durable_reason_tamper(tmp_path: Path) -> None:
    card, _hold_path = _refusal(tmp_path)
    journal_path = tmp_path / "refusal.sqlite"
    SpineBindHoldJournal(journal_path).append(card).get("digest")

    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        UPDATE spine_bind_hold
        SET hold_reason = ?
        WHERE tenant_id = ? AND outbox_id = ?
        """,
        ("rewritten", "house-a", "ob-1"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(
        SpineBindHoldReadError,
        match="does not match durable evidence",
    ):
        SpineBindHoldRead(journal_path).card("house-a", "ob-1")



def test_read_and_chain_reject_refusal_id_tamper(tmp_path: Path) -> None:
    card, _hold_path = _refusal(tmp_path)
    journal_path = tmp_path / "refusal.sqlite"
    journal = SpineBindHoldJournal(journal_path)
    sealed = journal.append(card)
    journal.close()

    chain = SpineBindHoldChain(journal_path)
    expected_chain = chain.seal("house-a")["digest"]
    chain.close()

    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        UPDATE spine_bind_hold
        SET refusal_id = ?
        WHERE refusal_id = ?
        """,
        (99, sealed["refusal_id"]),
    )
    connection.commit()
    connection.close()

    with pytest.raises(
        SpineBindHoldReadError,
        match="identity digest",
    ):
        SpineBindHoldRead(journal_path).card("house-a", "ob-1")

    with pytest.raises(
        SpineBindHoldChainError,
        match="identity digest",
    ):
        SpineBindHoldChain(journal_path).verify(
            "house-a",
            expected_chain,
        )

def test_legacy_unbound_refusal_row_fails_closed(tmp_path: Path) -> None:
    journal_path = tmp_path / "refusal.sqlite"
    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        CREATE TABLE spine_bind_hold (
            tenant_id TEXT NOT NULL,
            outbox_id TEXT NOT NULL,
            digest TEXT NOT NULL,
            held INTEGER NOT NULL,
            applied INTEGER NOT NULL,
            epoch INTEGER NOT NULL,
            PRIMARY KEY (tenant_id, outbox_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO spine_bind_hold(
            tenant_id, outbox_id, digest, held, applied, epoch
        ) VALUES (?, ?, ?, 1, 0, 1)
        """,
        ("house-a", "ob-1", "d" * 64),
    )
    connection.commit()
    connection.close()

    migrated = SpineBindHoldJournal(journal_path)
    migrated.close()
    with pytest.raises(
        SpineBindHoldReadError,
        match="missing bound hold identity",
    ):
        SpineBindHoldRead(journal_path).card("house-a", "ob-1")


def test_chain_reconstructs_rows_and_detects_tamper(tmp_path: Path) -> None:
    card, _hold_path = _refusal(tmp_path)
    journal_path = tmp_path / "refusal.sqlite"
    SpineBindHoldJournal(journal_path).append(card)
    chain = SpineBindHoldChain(journal_path)
    sealed = chain.seal("house-a")
    assert sealed["rows"] == 1
    assert sealed["applied"] == 0
    assert len(sealed["digest"]) == 64
    verified = chain.verify("house-a", sealed["digest"])
    assert verified["match"] is True
    assert verified["apply_authority"] is False
    chain.close()

    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        UPDATE spine_bind_hold
        SET bind_digest = ?
        WHERE tenant_id = ?
        """,
        ("e" * 64, "house-a"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(
        SpineBindHoldChainError,
        match="does not match durable evidence",
    ):
        SpineBindHoldChain(journal_path).seal("house-a")
