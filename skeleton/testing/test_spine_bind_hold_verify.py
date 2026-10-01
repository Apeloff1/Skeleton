from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from skeleton.persistence.spine_bind_hold import SpineBindHold
from skeleton.persistence.spine_bind_hold_journal import SpineBindHoldJournal
from skeleton.persistence.spine_bind_hold_verify import (
    SpineBindHoldVerify,
    SpineBindHoldVerifyError,
)
from skeleton.persistence.spine_hold import SpineHold


NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)


def _evidence(
    tmp_path: Path,
) -> tuple[dict[str, object], SpineBindHoldVerify, Path]:
    hold_path = tmp_path / "hold.sqlite"
    journal_path = tmp_path / "journal.sqlite"
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
        bind={
            "kind": "spine_bind_card",
            "tenant_id": "house-a",
            "apply_landed": False,
            "moved": False,
            "digest": "c" * 64,
        },
        epoch_before=7,
        epoch_after=7,
    )
    gate.close()
    journal = SpineBindHoldJournal(journal_path)
    journal.append(card)
    journal.close()
    return card, SpineBindHoldVerify(journal_path), journal_path


def test_bind_hold_refusal_is_independently_verified(
    tmp_path: Path,
) -> None:
    card, verifier, _path = _evidence(tmp_path)
    result = verifier.verify(card)
    assert result["verified"] is True
    assert result["refusal_id"] >= 1
    assert result["hold_id"] == card["hold_id"]
    assert result["hold_reason"] == "poison"
    assert result["bind_digest"] == "c" * 64
    assert len(result["refusal_digest"]) == 64
    assert result["apply_authority"] is False
    assert result["merge_authority"] is False
    verifier.close()


def test_bind_hold_verifier_rejects_card_identity_tamper(
    tmp_path: Path,
) -> None:
    card, verifier, _path = _evidence(tmp_path)
    tampered = copy.deepcopy(card)
    tampered["reason"] = "rewritten"
    with pytest.raises(
        SpineBindHoldVerifyError,
        match="identity mismatch",
    ):
        verifier.verify(tampered)
    verifier.close()


def test_bind_hold_verifier_rejects_durable_digest_tamper(
    tmp_path: Path,
) -> None:
    card, verifier, journal_path = _evidence(tmp_path)
    connection = sqlite3.connect(journal_path)
    connection.execute(
        """
        UPDATE spine_bind_hold
        SET digest = ?
        WHERE tenant_id = ? AND outbox_id = ?
        """,
        ("e" * 64, "house-a", "ob-1"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(
        SpineBindHoldVerifyError,
        match="digest mismatch",
    ):
        verifier.verify(card)
    verifier.close()



def test_bind_hold_verifier_rejects_refusal_id_tamper(
    tmp_path: Path,
) -> None:
    card, verifier, journal_path = _evidence(tmp_path)
    connection = sqlite3.connect(journal_path)
    connection.execute(
        "UPDATE spine_bind_hold SET refusal_id = 77"
    )
    connection.commit()
    connection.close()
    with pytest.raises(
        SpineBindHoldVerifyError,
        match="identity digest mismatch",
    ):
        verifier.verify(card)
    verifier.close()

def test_bind_hold_verifier_rejects_signoff_tamper(
    tmp_path: Path,
) -> None:
    card, verifier, _path = _evidence(tmp_path)
    tampered = copy.deepcopy(card)
    tampered["completion_checkbox"] = True
    with pytest.raises(
        SpineBindHoldVerifyError,
        match="overclaimed authority",
    ):
        verifier.verify(tampered)
    verifier.close()
