from __future__ import annotations

import hashlib

from skeleton.release.external_restore import (
    ExternalReferenceKind,
    ExternalRestoreReceipt,
    ExternalRestoreReference,
    qualify_external_restore,
)


def h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_external_restore_accepts_reconciled_resources_credentials_and_tombstones() -> None:
    refs = (
        ExternalRestoreReference(
            "credential:provider",
            ExternalReferenceKind.CREDENTIAL,
            h("credential-live"),
        ),
        ExternalRestoreReference(
            "resource:bucket",
            ExternalReferenceKind.EXTERNAL_RESOURCE,
            h("bucket-live"),
        ),
        ExternalRestoreReference(
            "tombstone:user-42",
            ExternalReferenceKind.TOMBSTONE,
            h("deleted"),
        ),
    )
    receipts = (
        ExternalRestoreReceipt(
            "credential:provider",
            h("credential-live"),
            reconciled=True,
            credential_revalidated=True,
        ),
        ExternalRestoreReceipt(
            "resource:bucket",
            h("bucket-live"),
            reconciled=True,
        ),
        ExternalRestoreReceipt(
            "tombstone:user-42",
            h("deleted"),
            reconciled=True,
            tombstone_propagated=True,
            resurrected=False,
        ),
    )

    decision = qualify_external_restore(references=refs, receipts=receipts)
    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.receipt_digests) == 3
    assert len(decision.decision_digest) == 64


def test_stale_restored_credential_blocks_until_revalidated() -> None:
    ref = ExternalRestoreReference(
        "credential:provider",
        ExternalReferenceKind.CREDENTIAL,
        h("credential-current"),
    )
    receipt = ExternalRestoreReceipt(
        "credential:provider",
        h("credential-current"),
        reconciled=True,
        credential_revalidated=False,
    )

    decision = qualify_external_restore(references=(ref,), receipts=(receipt,))
    assert decision.accepted is False
    assert "credential:provider:credential-not-revalidated" in decision.reasons


def test_external_resource_drift_blocks_local_restore_assumption() -> None:
    ref = ExternalRestoreReference(
        "resource:queue",
        ExternalReferenceKind.EXTERNAL_RESOURCE,
        h("queue-v2"),
    )
    receipt = ExternalRestoreReceipt(
        "resource:queue",
        h("queue-v1"),
        reconciled=True,
    )

    decision = qualify_external_restore(references=(ref,), receipts=(receipt,))
    assert decision.accepted is False
    assert "resource:queue:external-digest-mismatch" in decision.reasons


def test_tombstone_replay_must_propagate_and_never_resurrect() -> None:
    ref = ExternalRestoreReference(
        "tombstone:object-1",
        ExternalReferenceKind.TOMBSTONE,
        h("deleted"),
    )
    receipt = ExternalRestoreReceipt(
        "tombstone:object-1",
        h("deleted"),
        reconciled=True,
        tombstone_propagated=False,
        resurrected=True,
    )

    decision = qualify_external_restore(references=(ref,), receipts=(receipt,))
    assert decision.accepted is False
    assert "tombstone:object-1:tombstone-not-propagated" in decision.reasons
    assert "tombstone:object-1:tombstone-resurrected" in decision.reasons


def test_missing_external_reconciliation_blocks_every_reference_kind() -> None:
    for kind in ExternalReferenceKind:
        ref = ExternalRestoreReference("ref", kind, h("current"))
        receipt = ExternalRestoreReceipt(
            "ref",
            h("current"),
            reconciled=False,
            credential_revalidated=(kind is ExternalReferenceKind.CREDENTIAL),
            tombstone_propagated=(kind is ExternalReferenceKind.TOMBSTONE),
        )
        decision = qualify_external_restore(
            references=(ref,),
            receipts=(receipt,),
        )
        assert decision.accepted is False
        assert "ref:external-not-reconciled" in decision.reasons


def test_missing_receipt_blocks_restore_qualification() -> None:
    ref = ExternalRestoreReference(
        "resource:remote",
        ExternalReferenceKind.EXTERNAL_RESOURCE,
        h("remote"),
    )
    decision = qualify_external_restore(references=(ref,), receipts=())
    assert decision.accepted is False
    assert "resource:remote:receipt-cardinality" in decision.reasons
