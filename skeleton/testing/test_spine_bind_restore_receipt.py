from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_bind_restore_receipt import (
    SpineBindRestoreReceipt,
    SpineBindRestoreReceiptError,
)
from skeleton.persistence.spine_bind_restore_verify import (
    SpineBindRestoreVerify,
    SpineBindRestoreVerifyError,
)


TENANT = "tenant-restore-receipt"
RECOVERY = "a" * 64
BACKUP = "b" * 64
CHAIN = "c" * 64
BUNDLE = "d" * 64


def _cards():
    checkpoint = {
        "kind": "spine_bind_checkpoint",
        "tenant_id": TENANT,
        "seen": True,
        "recovery_digest": RECOVERY,
        "snapshot_digest": "e" * 64,
        "activated": False,
    }
    replay = {
        "kind": "spine_bind_checkpoint_replay",
        "tenant_id": TENANT,
        "recovery_digest": RECOVERY,
        "rows_before": 1,
        "rows_after": 1,
        "inserted": False,
        "rewritten": False,
        "activated": False,
    }
    tenant = {
        "kind": "spine_bind_checkpoint_tenant",
        "tenant_id": TENANT,
        "count": 1,
        "digests": [RECOVERY],
        "foreign": 0,
        "activated": False,
    }
    chain = {
        "kind": "spine_bind_checkpoint_chain",
        "tenant_id": TENANT,
        "rows": 1,
        "digest": CHAIN,
        "rewritten": False,
        "activated": False,
    }
    bundle = {
        "kind": "spine_bind_bundle",
        "tenant_id": TENANT,
        "recovery_digest": RECOVERY,
        "digest": BUNDLE,
        "activated": False,
    }
    verified = {
        "kind": "spine_bind_bundle_verify",
        "tenant_id": TENANT,
        "bundle_digest": BUNDLE,
        "verified": True,
        "activated": False,
    }
    return checkpoint, replay, tenant, chain, bundle, verified


def _receipt():
    checkpoint, replay, tenant, chain, bundle, verified = _cards()
    return SpineBindRestoreReceipt().card(
        backup_digest=BACKUP,
        restore_digest=BACKUP,
        expected_recovery_digest=RECOVERY,
        checkpoint=checkpoint,
        replay=replay,
        tenant=tenant,
        chain=chain,
        bundle=bundle,
        verified=verified,
    )


def test_restore_receipt_anchors_recovery_without_activation() -> None:
    receipt = _receipt()
    result = SpineBindRestoreVerify().verify(receipt)

    assert receipt["backup_restore_digest"] == BACKUP
    assert receipt["recovery_digest"] == RECOVERY
    assert receipt["checkpoint_rows"] == 1
    assert receipt["restored"] is True
    assert receipt["verified"] is True
    assert receipt["activated"] is False
    assert receipt["apply_landed"] is False
    assert receipt["ci_green"] is False
    assert receipt["merged"] is False
    assert result["verified"] is True
    assert result["activated"] is False
    assert result["completion_checkbox"] is False


def test_restore_receipt_rejects_backup_restore_mismatch() -> None:
    checkpoint, replay, tenant, chain, bundle, verified = _cards()

    with pytest.raises(
        SpineBindRestoreReceiptError,
        match="backup and restore digests differ",
    ):
        SpineBindRestoreReceipt().card(
            backup_digest=BACKUP,
            restore_digest="f" * 64,
            expected_recovery_digest=RECOVERY,
            checkpoint=checkpoint,
            replay=replay,
            tenant=tenant,
            chain=chain,
            bundle=bundle,
            verified=verified,
        )


def test_restore_receipt_rejects_changed_recovery_digest() -> None:
    checkpoint, replay, tenant, chain, bundle, verified = _cards()
    checkpoint["recovery_digest"] = "f" * 64

    with pytest.raises(
        SpineBindRestoreReceiptError,
        match="restored recovery digest changed",
    ):
        SpineBindRestoreReceipt().card(
            backup_digest=BACKUP,
            restore_digest=BACKUP,
            expected_recovery_digest=RECOVERY,
            checkpoint=checkpoint,
            replay=replay,
            tenant=tenant,
            chain=chain,
            bundle=bundle,
            verified=verified,
        )


def test_restore_receipt_rejects_replay_insertion() -> None:
    checkpoint, replay, tenant, chain, bundle, verified = _cards()
    replay["inserted"] = True

    with pytest.raises(
        SpineBindRestoreReceiptError,
        match="replay mutated checkpoint",
    ):
        SpineBindRestoreReceipt().card(
            backup_digest=BACKUP,
            restore_digest=BACKUP,
            expected_recovery_digest=RECOVERY,
            checkpoint=checkpoint,
            replay=replay,
            tenant=tenant,
            chain=chain,
            bundle=bundle,
            verified=verified,
        )


def test_restore_verifier_rejects_tamper() -> None:
    receipt = copy.deepcopy(_receipt())
    receipt["ci_green"] = True

    with pytest.raises(
        SpineBindRestoreVerifyError,
        match="restore receipt digest mismatch",
    ):
        SpineBindRestoreVerify().verify(receipt)
