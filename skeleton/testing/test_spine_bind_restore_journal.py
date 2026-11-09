from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_restore_chain import (
    SpineBindRestoreChain,
    SpineBindRestoreChainError,
)
from skeleton.persistence.spine_bind_restore_continuity import (
    SpineBindRestoreContinuity,
    SpineBindRestoreContinuityError,
)
from skeleton.persistence.spine_bind_restore_journal import (
    SpineBindRestoreJournal,
    SpineBindRestoreJournalError,
)
from skeleton.persistence.spine_bind_restore_replay import SpineBindRestoreReplay
from skeleton.persistence.spine_bind_restore_tenant import SpineBindRestoreTenant


BASE = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)
TENANT = "tenant-restore-journal"


def _receipt(*, backup: str = "b" * 64, bundle: str = "d" * 64):
    body = {
        "kind": "spine_bind_restore_receipt",
        "hit": True,
        "law": "restore-receipt-is-not-activation",
        "citation": "VOL-134",
        "tenant_id": TENANT,
        "backup_restore_digest": backup,
        "recovery_digest": "a" * 64,
        "checkpoint_rows": 1,
        "chain_digest": "c" * 64,
        "bundle_digest": bundle,
        "restored": True,
        "verified": True,
        "activated": False,
        "apply_landed": False,
        "live_motor": False,
        "dispatcher_running": False,
        "provider_surface_green": False,
        "pr_automation_green": False,
        "ci_green": False,
        "merged": False,
        "stored_prose": 0,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return body


def test_restore_journal_is_idempotent_isolated_chained_and_continuous(
    tmp_path: Path,
) -> None:
    path = tmp_path / "restore.sqlite"
    receipt = _receipt()
    journal_store = SpineBindRestoreJournal(path)

    first = journal_store.append(receipt, now=BASE)
    second = journal_store.append(receipt, now=BASE)

    assert first["inserted"] is True
    assert second["inserted"] is False
    assert first["journal_id"] == second["journal_id"]
    assert first["row_digest"] == second["row_digest"]
    assert journal_store.count(TENANT) == 1

    replay = SpineBindRestoreReplay(path).replay(first)
    own = SpineBindRestoreTenant(path).card(TENANT)
    foreign = SpineBindRestoreTenant(path).card("tenant-foreign")
    chain = SpineBindRestoreChain(path).seal(TENANT)
    continuity = SpineBindRestoreContinuity().card(
        receipt=receipt,
        journal=first,
        replay=replay,
        tenant=own,
        chain=chain,
    )

    assert replay["rows_before"] == 1
    assert replay["rows_after"] == 1
    assert replay["inserted"] is False
    assert own["count"] == 1
    assert own["foreign"] == 0
    assert foreign["count"] == 0
    assert foreign["receipt_digests"] == []
    assert chain["rows"] == 1
    assert chain["head_receipt_digest"] == receipt["digest"]
    assert continuity["durable"] is True
    assert continuity["tenant_isolated"] is True
    assert continuity["replay_safe"] is True
    assert continuity["activated"] is False
    assert continuity["completion_checkbox"] is False

    journal_store.close()


def test_restore_journal_links_multiple_receipts_per_tenant(tmp_path: Path) -> None:
    path = tmp_path / "restore.sqlite"
    store = SpineBindRestoreJournal(path)
    first_receipt = _receipt()
    second_receipt = _receipt(backup="e" * 64, bundle="f" * 64)

    first = store.append(first_receipt, now=BASE)
    second = store.append(
        second_receipt,
        now=datetime(2026, 10, 1, 13, 1, tzinfo=timezone.utc),
    )

    assert first["previous_digest"] == "0" * 64
    assert second["previous_digest"] == first_receipt["digest"]
    assert store.count(TENANT) == 2

    tenant = SpineBindRestoreTenant(path).card(TENANT)
    chain = SpineBindRestoreChain(path).seal(TENANT)
    assert tenant["receipt_digests"] == [
        first_receipt["digest"],
        second_receipt["digest"],
    ]
    assert chain["rows"] == 2
    assert chain["head_receipt_digest"] == second_receipt["digest"]


def test_restore_journal_rejects_tampered_receipt(tmp_path: Path) -> None:
    receipt = _receipt()
    receipt["ci_green"] = True

    with pytest.raises(SpineBindRestoreJournalError, match="not dark"):
        SpineBindRestoreJournal(tmp_path / "restore.sqlite").append(receipt, now=BASE)


def test_restore_chain_detects_row_mutation(tmp_path: Path) -> None:
    path = tmp_path / "restore.sqlite"
    store = SpineBindRestoreJournal(path)
    store.append(_receipt(), now=BASE)
    store._connection.execute(
        """
        UPDATE spine_bind_restore_receipt
        SET bundle_digest = ?
        WHERE tenant_id = ?
        """,
        ("f" * 64, TENANT),
    )
    store._connection.commit()

    with pytest.raises(SpineBindRestoreChainError, match="row digest mismatch"):
        SpineBindRestoreChain(path).seal(TENANT)


def test_restore_continuity_rejects_wrong_chain_head(tmp_path: Path) -> None:
    path = tmp_path / "restore.sqlite"
    receipt = _receipt()
    store = SpineBindRestoreJournal(path)
    journal = store.append(receipt, now=BASE)
    replay = SpineBindRestoreReplay(path).replay(journal)
    tenant = SpineBindRestoreTenant(path).card(TENANT)
    chain = SpineBindRestoreChain(path).seal(TENANT)
    bad_chain = copy.deepcopy(chain)
    bad_chain["head_receipt_digest"] = "f" * 64

    with pytest.raises(
        SpineBindRestoreContinuityError,
        match="restore chain head mismatch",
    ):
        SpineBindRestoreContinuity().card(
            receipt=receipt,
            journal=journal,
            replay=replay,
            tenant=tenant,
            chain=bad_chain,
        )
