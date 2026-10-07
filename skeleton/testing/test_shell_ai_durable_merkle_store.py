"""Immutable durable session Merkle bundle store tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_merkle import DurableMerkleAuthority
from skeleton.shells.ai.durable_merkle_session import (
    DurableSessionMerkleAuthority,
)
from skeleton.shells.ai.durable_merkle_store import (
    DurableMerkleBundleConflict,
    DurableMerkleBundleCorruption,
    DurableMerkleBundleIndex,
    DurableMerkleBundleStoreError,
    DurableSessionMerkleBundleStore,
)
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.session_evidence import (
    SessionExecutionEvidence,
    SessionReceiptEvidence,
)
from skeleton.shells.ai.session_integrity import SessionEvidenceIntegrityVerifier
from skeleton.shells.ai.session_journal import SessionJournalEvidence
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def build_bundle(
    *,
    finalization_id="finalization",
    session_id="session",
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    journal.append(
        "planned",
        session_id=session_id,
        intent_id="intent",
        proposal_id="proposal",
    )
    journal.append(
        "complete",
        session_id=session_id,
        intent_id="intent",
        proposal_id="proposal",
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    receipt = ExecutionReceipt(
        command="python",
        correlation_id="corr",
        fingerprint=fp("a"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id="receipt-one",
    )
    receipts.append(receipt)
    session_journal = SessionJournalEvidence.from_journal(
        journal,
        session_id,
    )
    session_evidence = SessionExecutionEvidence(
        1,
        session_id,
        "plan",
        fp("p"),
        True,
        (
            SessionReceiptEvidence(
                "step",
                "corr",
                (receipt.receipt_id,),
                (receipt.fingerprint,),
                (receipt.returncode,),
                1,
                True,
            ),
        ),
    )
    integrity = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        session_journal,
        session_evidence,
    )
    checkpoint = AISessionCheckpoint(
        1,
        session_id,
        "complete",
        "intent",
        fp("i"),
        "proposal",
        fp("q"),
        6,
        integrity.journal_root,
        integrity.receipt_root,
        fp("p"),
        fp("t"),
        fp("e"),
    )
    recovery = AIRecoveryCheckpoint.wrap(
        checkpoint,
        session_evidence_digest=session_evidence.digest,
        session_journal_digest=session_journal.digest,
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("x"),
        session_integrity_digest=integrity.digest,
    )
    merkle = DurableMerkleAuthority(
        ArtifactSigner(
            "merkle",
            b"k" * 32,
            clock=lambda: 10.0,
        )
    )
    authority = DurableSessionMerkleAuthority(
        merkle,
        journal_chain_id="journal-main",
        receipt_chain_id="receipts-main",
    )
    bundle = authority.build(
        finalization_id=finalization_id,
        session_id=session_id,
        recovery=recovery,
        integrity=integrity,
        session_journal=session_journal,
        session_evidence=session_evidence,
        journal_chain=journal,
        receipt_chain=receipts,
    )
    return (
        bundle,
        backend,
        journal,
        receipts,
        recovery,
        integrity,
        session_journal,
        session_evidence,
        authority,
    )


def test_put_once_creates_bundle_and_index():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    commit = store.put_once(bundle)
    assert commit.bundle_created
    assert commit.index_created
    assert commit.stored.bundle == bundle
    assert commit.index.index.bundle_digest == bundle.digest
    assert (
        commit.index.index.finalization_id
        == bundle.finalization_id
    )


def test_put_once_is_idempotent():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    first = store.put_once(bundle)
    second = store.put_once(bundle)
    assert not second.bundle_created
    assert not second.index_created
    assert second.stored == first.stored
    assert second.index == first.index


def test_get_by_digest():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    store.put_once(bundle)
    stored = store.get_by_digest(
        bundle.digest
    )
    assert stored is not None
    assert stored.bundle == bundle


def test_get_by_digest_missing():
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    assert store.get_by_digest(
        fp("a")
    ) is None


def test_get_by_finalization():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    store.put_once(bundle)
    stored = store.get_by_finalization(
        bundle.finalization_id
    )
    assert stored is not None
    assert stored.bundle == bundle


def test_get_by_finalization_missing():
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    assert store.get_by_finalization(
        "missing"
    ) is None


def test_require_finalization():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    store.put_once(bundle)
    stored = store.require_finalization(
        bundle.finalization_id,
        bundle_digest=bundle.digest,
    )
    assert stored.bundle == bundle


def test_require_finalization_missing():
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DurableMerkleBundleStoreError,
        match="missing",
    ):
        store.require_finalization(
            "missing"
        )


def test_require_finalization_wrong_digest():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    store.put_once(bundle)
    with pytest.raises(
        DurableMerkleBundleConflict,
        match="differs",
    ):
        store.require_finalization(
            bundle.finalization_id,
            bundle_digest=fp("f"),
        )


def test_same_finalization_cannot_bind_different_bundle():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    store.put_once(bundle)
    other = replace(
        bundle,
        session_integrity_digest=fp("f"),
    )
    assert other.digest != bundle.digest
    with pytest.raises(
        DurableMerkleBundleConflict,
        match="different",
    ):
        store.put_once(other)


def test_different_finalizations_can_store_independently():
    first, *_ = build_bundle(
        finalization_id="first"
    )
    second, *_ = build_bundle(
        finalization_id="second"
    )
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    first_commit = store.put_once(first)
    second_commit = store.put_once(second)
    assert (
        first_commit.stored.bundle.digest
        != second_commit.stored.bundle.digest
    )
    assert (
        store.require_finalization(
            "first"
        ).bundle == first
    )
    assert (
        store.require_finalization(
            "second"
        ).bundle == second
    )


def test_index_from_bundle():
    bundle, *_ = build_bundle()
    index = DurableMerkleBundleIndex.from_bundle(
        bundle
    )
    assert index.finalization_id == bundle.finalization_id
    assert index.session_id == bundle.session_id
    assert index.bundle_digest == bundle.digest
    assert (
        index.recovery_checkpoint_digest
        == bundle.recovery_checkpoint_digest
    )
    assert (
        index.session_integrity_digest
        == bundle.session_integrity_digest
    )
    assert (
        index.journal_checkpoint_digest
        == bundle.journal_checkpoint.digest
    )
    assert (
        index.receipt_checkpoint_digest
        == bundle.receipt_checkpoint.digest
    )


def test_index_to_dict():
    bundle, *_ = build_bundle()
    index = DurableMerkleBundleIndex.from_bundle(
        bundle
    )
    data = index.to_dict()
    assert data["finalization_id"] == "finalization"
    assert data["session_id"] == "session"
    assert data["bundle_digest"] == bundle.digest


def test_verify_index_true_for_healthy_bundle():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    store.put_once(bundle)
    assert store.verify_index(
        bundle.finalization_id
    )


def test_verify_index_false_for_missing_bundle():
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    assert not store.verify_index(
        "missing"
    )


def test_bundle_written_without_index_can_be_repaired():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    backend.put_if_absent(
        "merkle",
        store._bundle_key(
            bundle.digest
        ),
        bundle,
    )
    assert (
        store.get_by_finalization(
            bundle.finalization_id
        )
        is None
    )
    repaired = store.repair_index(
        bundle.digest
    )
    assert (
        repaired.index.bundle_digest
        == bundle.digest
    )
    assert (
        store.require_finalization(
            bundle.finalization_id
        ).bundle
        == bundle
    )


def test_repair_index_missing_bundle_fails():
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DurableMerkleBundleStoreError,
        match="missing",
    ):
        store.repair_index(
            fp("a")
        )


def test_index_to_missing_bundle_is_corruption():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    index = DurableMerkleBundleIndex.from_bundle(
        bundle
    )
    backend.put_if_absent(
        "merkle",
        store._finalization_key(
            bundle.finalization_id
        ),
        index,
    )
    with pytest.raises(
        DurableMerkleBundleCorruption,
        match="missing bundle",
    ):
        store.get_by_finalization(
            bundle.finalization_id
        )


def test_wrong_bundle_value_type_is_corruption():
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    backend.put_if_absent(
        "merkle",
        store._bundle_key(
            fp("a")
        ),
        {"bad": True},
    )
    with pytest.raises(
        DurableMerkleBundleCorruption,
        match="value type",
    ):
        store.get_by_digest(
            fp("a")
        )


def test_wrong_index_value_type_is_corruption():
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    backend.put_if_absent(
        "merkle",
        store._finalization_key(
            "finalization"
        ),
        {"bad": True},
    )
    with pytest.raises(
        DurableMerkleBundleCorruption,
        match="invalid value type",
    ):
        store.index(
            "finalization"
        )


def test_content_addressed_bundle_digest_mismatch_is_corruption():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    backend.put_if_absent(
        "merkle",
        store._bundle_key(
            fp("f")
        ),
        bundle,
    )
    with pytest.raises(
        DurableMerkleBundleCorruption,
        match="digest mismatch",
    ):
        store.get_by_digest(
            fp("f")
        )


def test_index_metadata_substitution_is_corruption():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    store.put_once(bundle)
    key = store._finalization_key(
        bundle.finalization_id
    )
    record = backend.get(
        "merkle",
        key,
    )
    tampered = replace(
        record.value,
        session_integrity_digest=fp("f"),
    )
    backend.compare_and_swap(
        "merkle",
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableMerkleBundleCorruption,
        match="metadata differs",
    ):
        store.get_by_finalization(
            bundle.finalization_id
        )


def test_finalization_index_identity_substitution_is_corruption():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    store = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    index = DurableMerkleBundleIndex.from_bundle(
        bundle
    )
    key = store._finalization_key(
        bundle.finalization_id
    )
    backend.put_if_absent(
        "merkle",
        key,
        replace(
            index,
            finalization_id="other",
        ),
    )
    with pytest.raises(
        DurableMerkleBundleCorruption,
        match="identity mismatch",
    ):
        store.index(
            bundle.finalization_id
        )


def test_put_once_rejects_non_bundle():
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    with pytest.raises(
        TypeError,
        match="DurableSessionMerkleProofBundle",
    ):
        store.put_once(
            object()
        )


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_namespace_validation(namespace):
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableSessionMerkleBundleStore(
            InMemoryFencedStore(),
            namespace=namespace,
        )


def test_bundle_key_hides_nothing_but_is_content_addressed():
    key = DurableSessionMerkleBundleStore._bundle_key(
        fp("a")
    )
    assert key == "bundle:" + fp("a")


def test_finalization_key_hides_raw_identity():
    key = DurableSessionMerkleBundleStore._finalization_key(
        "sensitive-finalization"
    )
    assert key.startswith(
        "finalization:"
    )
    assert (
        "sensitive-finalization"
        not in key
    )
    assert key == (
        DurableSessionMerkleBundleStore
        ._finalization_key(
            "sensitive-finalization"
        )
    )


def test_bundle_key_rejects_bad_digest():
    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        DurableSessionMerkleBundleStore._bundle_key(
            "bad"
        )


def test_finalization_key_rejects_empty_id():
    with pytest.raises(
        ValueError,
        match="finalization_id",
    ):
        DurableSessionMerkleBundleStore._finalization_key(
            ""
        )


def test_commit_to_dict():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    commit = store.put_once(bundle)
    data = commit.to_dict()
    assert data["bundle_created"] is True
    assert data["index_created"] is True
    assert (
        data["stored"]["bundle"]["digest"]
        == bundle.digest
    )
    assert (
        data["index"]["index"]["bundle_digest"]
        == bundle.digest
    )


def test_fresh_store_reader_resolves_existing_bundle():
    bundle, *_ = build_bundle()
    backend = InMemoryFencedStore()
    first = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    first.put_once(bundle)
    second = DurableSessionMerkleBundleStore(
        backend,
        namespace="merkle",
    )
    assert (
        second.require_finalization(
            bundle.finalization_id
        ).bundle
        == bundle
    )


def test_store_preserves_signature_bytes_exactly():
    bundle, *_ = build_bundle()
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    stored = store.put_once(
        bundle
    ).stored.bundle
    assert (
        stored.journal_checkpoint.signature
        == bundle.journal_checkpoint.signature
    )
    assert (
        stored.receipt_checkpoint.signature
        == bundle.receipt_checkpoint.signature
    )


def test_index_supports_zero_receipt_bundle():
    bundle, backend, journal, receipts, recovery, integrity, session_journal, session_evidence, authority = build_bundle()
    no_receipt_evidence = replace(
        session_evidence,
        steps=(),
    )
    empty_backend = InMemoryFencedStore()
    empty_journal = DistributedAIDecisionJournal(
        empty_backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    empty_journal.append(
        "planned",
        session_id="session-zero",
        intent_id="intent",
        proposal_id="proposal",
    )
    empty_receipts = DistributedReceiptChain(
        empty_backend,
        namespace="receipts",
    )
    zero_journal = SessionJournalEvidence.from_journal(
        empty_journal,
        "session-zero",
    )
    zero_evidence = SessionExecutionEvidence(
        1,
        "session-zero",
        "plan",
        fp("p"),
        True,
        (),
    )
    zero_integrity = SessionEvidenceIntegrityVerifier(
        empty_journal,
        empty_receipts,
    ).require(
        zero_journal,
        zero_evidence,
    )
    zero_checkpoint = AISessionCheckpoint(
        1,
        "session-zero",
        "complete",
        "intent",
        fp("i"),
        "proposal",
        fp("q"),
        6,
        zero_integrity.journal_root,
        zero_integrity.receipt_root,
        fp("p"),
        fp("t"),
        fp("e"),
    )
    zero_recovery = AIRecoveryCheckpoint.wrap(
        zero_checkpoint,
        session_evidence_digest=zero_evidence.digest,
        session_journal_digest=zero_journal.digest,
        session_integrity_digest=zero_integrity.digest,
    )
    zero_authority = DurableSessionMerkleAuthority(
        DurableMerkleAuthority(
            ArtifactSigner(
                "merkle",
                b"k" * 32,
                clock=lambda: 10.0,
            )
        ),
        journal_chain_id="journal-main",
        receipt_chain_id="receipts-main",
    )
    zero_bundle = zero_authority.build(
        finalization_id="zero-finalization",
        session_id="session-zero",
        recovery=zero_recovery,
        integrity=zero_integrity,
        session_journal=zero_journal,
        session_evidence=zero_evidence,
        journal_chain=empty_journal,
        receipt_chain=empty_receipts,
    )
    index = DurableMerkleBundleIndex.from_bundle(
        zero_bundle
    )
    assert index.receipt_checkpoint_digest == ""
    store = DurableSessionMerkleBundleStore(
        InMemoryFencedStore()
    )
    assert store.put_once(
        zero_bundle
    ).index.index == index
