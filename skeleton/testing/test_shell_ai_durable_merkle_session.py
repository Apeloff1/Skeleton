"""Session-bound durable Merkle proof bundle tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.checkpoint import (
    AISessionCheckpoint,
)
from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_merkle import (
    DurableMerkleAuthority,
    DurableMerkleChainKind,
    DurableMerkleProof,
)
from skeleton.shells.ai.durable_merkle_session import (
    DurableSessionMerkleAuthority,
    DurableSessionMerkleError,
    DurableSessionMerkleProofBundle,
)
from skeleton.shells.ai.recovery_checkpoint import (
    AIRecoveryCheckpoint,
)
from skeleton.shells.ai.session_evidence import (
    SessionExecutionEvidence,
    SessionReceiptEvidence,
)
from skeleton.shells.ai.session_integrity import (
    SessionEvidenceIntegrityVerifier,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvidence,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import (
    ExecutionReceipt,
)


def fp(char: str) -> str:
    return char * 64


def receipt(
    name: str,
    *,
    correlation_id="corr",
    fingerprint=None,
    attempt=1,
    returncode=0,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=correlation_id,
        fingerprint=(
            fingerprint
            or fp(
                chr(
                    ord("a")
                    + attempt - 1
                )
            )
        ),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=returncode,
        ok=returncode == 0,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=attempt,
        receipt_id=f"receipt-{name}",
    )


def merkle_authority():
    return DurableMerkleAuthority(
        ArtifactSigner(
            "merkle",
            b"k" * 32,
            clock=lambda: 100.0,
        )
    )


def session_authority():
    return DurableSessionMerkleAuthority(
        merkle_authority(),
        journal_chain_id="journal-main",
        receipt_chain_id="receipts-main",
    )


class Fixture:
    def __init__(
        self,
        *,
        with_receipts=True,
        journal_events=3,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = (
            DistributedAIDecisionJournal(
                self.backend,
                namespace="journal",
                clock=lambda: 10.0,
            )
        )
        for index in range(
            1,
            journal_events + 1,
        ):
            self.journal.append(
                f"session.event.{index}",
                session_id="session",
                intent_id="intent",
                proposal_id="proposal",
                summary=f"event {index}",
                data={"index": index},
            )
            if index == 1:
                self.journal.append(
                    "unrelated.event",
                    session_id="other",
                    intent_id="other",
                    proposal_id="other",
                    summary="other",
                )

        self.receipts = (
            DistributedReceiptChain(
                self.backend,
                namespace="receipts",
            )
        )
        self.receipt_values = []
        if with_receipts:
            one = receipt(
                "one",
                attempt=1,
                fingerprint=fp("a"),
            )
            two = receipt(
                "two",
                attempt=2,
                fingerprint=fp("b"),
            )
            self.receipts.append(one)
            self.receipts.append(
                receipt(
                    "unrelated",
                    correlation_id="other",
                    attempt=1,
                    fingerprint=fp("c"),
                )
            )
            self.receipts.append(two)
            self.receipt_values = [
                one,
                two,
            ]
            steps = (
                SessionReceiptEvidence(
                    "step",
                    "corr",
                    (
                        one.receipt_id,
                        two.receipt_id,
                    ),
                    (
                        one.fingerprint,
                        two.fingerprint,
                    ),
                    (
                        one.returncode,
                        two.returncode,
                    ),
                    2,
                    True,
                ),
            )
        else:
            steps = ()

        self.session_journal = (
            SessionJournalEvidence.from_journal(
                self.journal,
                "session",
            )
        )
        self.session_evidence = (
            SessionExecutionEvidence(
                1,
                "session",
                "plan",
                fp("p"),
                True,
                steps,
            )
        )
        self.integrity = (
            SessionEvidenceIntegrityVerifier(
                self.journal,
                self.receipts,
            ).require(
                self.session_journal,
                self.session_evidence,
            )
        )
        self.checkpoint = (
            AISessionCheckpoint(
                1,
                "session",
                "complete",
                "intent",
                fp("i"),
                "proposal",
                fp("q"),
                6,
                self.integrity.journal_root,
                self.integrity.receipt_root,
                fp("p"),
                fp("t"),
                fp("e"),
            )
        )
        self.recovery = (
            AIRecoveryCheckpoint.wrap(
                self.checkpoint,
                session_evidence_digest=(
                    self.session_evidence.digest
                ),
                session_journal_digest=(
                    self.session_journal.digest
                ),
                release_evidence_digest=fp("l"),
                runtime_trust_digest=fp("u"),
                authority_health_policy_digest=fp("h"),
                execution_attempt_id="attempt",
                execution_attempt_authority_digest=fp("a"),
                session_integrity_digest=(
                    self.integrity.digest
                ),
            )
        )
        self.authority = session_authority()

    def build(self):
        return self.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=self.recovery,
            integrity=self.integrity,
            session_journal=self.session_journal,
            session_evidence=self.session_evidence,
            journal_chain=self.journal,
            receipt_chain=self.receipts,
        )


def test_build_session_bundle_with_receipts():
    fixture = Fixture()
    bundle = fixture.build()
    assert bundle.finalization_id == "finalization"
    assert bundle.session_id == "session"
    assert (
        bundle.recovery_checkpoint_digest
        == fixture.recovery.digest
    )
    assert (
        bundle.session_integrity_digest
        == fixture.integrity.digest
    )
    assert len(bundle.journal_proofs) == 3
    assert len(bundle.receipt_proofs) == 2
    assert bundle.receipt_checkpoint is not None


def test_journal_proofs_match_session_events_only():
    fixture = Fixture()
    bundle = fixture.build()
    expected = {
        event.global_sequence
        for event in fixture.session_journal.events
    }
    assert {
        proof.sequence
        for proof in bundle.journal_proofs
    } == expected
    assert len(expected) == 3


def test_receipt_proofs_match_integrity_inclusions_only():
    fixture = Fixture()
    bundle = fixture.build()
    expected = {
        item.global_sequence
        for item in fixture.integrity.receipt_inclusions
    }
    assert {
        proof.sequence
        for proof in bundle.receipt_proofs
    } == expected
    assert len(expected) == 2


def test_bundle_verifies_with_authoritative_chains():
    fixture = Fixture()
    bundle = fixture.build()
    report = fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=fixture.receipts,
    )
    assert report.ok
    assert report.identity_valid
    assert report.recovery_binding_valid
    assert report.integrity_binding_valid
    assert report.journal_checkpoint_valid
    assert report.journal_proofs_valid
    assert report.receipt_checkpoint_valid
    assert report.receipt_proofs_valid


def test_bundle_verifies_without_chain_access():
    fixture = Fixture()
    bundle = fixture.build()
    report = fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=None,
        receipt_chain=None,
    )
    assert report.ok


def test_zero_receipt_session_omits_receipt_checkpoint():
    fixture = Fixture(
        with_receipts=False
    )
    bundle = fixture.build()
    assert bundle.receipt_checkpoint is None
    assert bundle.receipt_proofs == ()
    assert (
        bundle.receipt_chain_root
        == fixture.recovery.session.receipt_root
    )
    report = fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=fixture.receipts,
    )
    assert report.ok


def test_later_journal_growth_does_not_break_bundle():
    fixture = Fixture()
    bundle = fixture.build()
    old_root = bundle.journal_chain_root
    fixture.journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    assert (
        fixture.journal.root_hash()
        != old_root
    )
    report = fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=fixture.receipts,
    )
    assert report.ok


def test_later_receipt_growth_does_not_break_bundle():
    fixture = Fixture()
    bundle = fixture.build()
    old_root = bundle.receipt_chain_root
    fixture.receipts.append(
        receipt(
            "later",
            correlation_id="later",
            fingerprint=fp("f"),
        )
    )
    assert (
        fixture.receipts.root_hash()
        != old_root
    )
    report = fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=fixture.receipts,
    )
    assert report.ok


def test_later_growth_on_both_chains_does_not_break_bundle():
    fixture = Fixture()
    bundle = fixture.build()
    fixture.journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    fixture.receipts.append(
        receipt(
            "later",
            correlation_id="later",
            fingerprint=fp("f"),
        )
    )
    assert fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=fixture.receipts,
    ).ok


def test_wrong_finalization_id_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    report = fixture.authority.inspect(
        bundle,
        finalization_id="other-finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.identity_valid


def test_wrong_session_id_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    report = fixture.authority.inspect(
        bundle,
        finalization_id="finalization",
        session_id="other-session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.identity_valid


def test_recovery_digest_substitution_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    bad = replace(
        bundle,
        recovery_checkpoint_digest=fp("f"),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.recovery_binding_valid


def test_integrity_digest_substitution_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    bad = replace(
        bundle,
        session_integrity_digest=fp("f"),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.integrity_binding_valid


def test_missing_journal_proof_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    bad = replace(
        bundle,
        journal_proofs=(
            bundle.journal_proofs[:-1]
        ),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.journal_proofs_valid
    assert any(
        "sequence set mismatch" in issue
        for issue in report.issues
    )


def test_missing_receipt_proof_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    bad = replace(
        bundle,
        receipt_proofs=(
            bundle.receipt_proofs[:-1]
        ),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.receipt_proofs_valid


def test_extra_journal_proof_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    unrelated_sequence = next(
        event.sequence
        for event in fixture.journal.snapshot()
        if event.session_id == "other"
    )
    signed = bundle.journal_checkpoint
    _, leaves = merkle_authority().build(
        fixture.journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        root_hash=fixture.recovery.session.journal_root,
    )
    extra = fixture.authority.merkle.prove(
        signed,
        leaves,
        sequence=unrelated_sequence,
    )
    bad = replace(
        bundle,
        journal_proofs=(
            *bundle.journal_proofs,
            extra,
        ),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.journal_proofs_valid


def test_duplicate_journal_proof_rejected_by_bundle():
    fixture = Fixture()
    bundle = fixture.build()
    with pytest.raises(
        ValueError,
        match="duplicate journal",
    ):
        replace(
            bundle,
            journal_proofs=(
                *bundle.journal_proofs,
                bundle.journal_proofs[0],
            ),
        )


def test_duplicate_receipt_proof_rejected_by_bundle():
    fixture = Fixture()
    bundle = fixture.build()
    with pytest.raises(
        ValueError,
        match="duplicate receipt",
    ):
        replace(
            bundle,
            receipt_proofs=(
                *bundle.receipt_proofs,
                bundle.receipt_proofs[0],
            ),
        )


def test_journal_signature_tamper_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    bad_signature = replace(
        bundle.journal_checkpoint.signature,
        signature=fp("f"),
    )
    bad_checkpoint = replace(
        bundle.journal_checkpoint,
        signature=bad_signature,
    )
    bad_proofs = tuple(
        replace(
            proof,
            checkpoint_digest=(
                bad_checkpoint.digest
            ),
        )
        for proof in bundle.journal_proofs
    )
    bad = replace(
        bundle,
        journal_checkpoint=bad_checkpoint,
        journal_proofs=bad_proofs,
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.journal_checkpoint_valid


def test_receipt_signature_tamper_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    bad_signature = replace(
        bundle.receipt_checkpoint.signature,
        signature=fp("f"),
    )
    bad_checkpoint = replace(
        bundle.receipt_checkpoint,
        signature=bad_signature,
    )
    bad_proofs = tuple(
        replace(
            proof,
            checkpoint_digest=(
                bad_checkpoint.digest
            ),
        )
        for proof in bundle.receipt_proofs
    )
    bad = replace(
        bundle,
        receipt_checkpoint=bad_checkpoint,
        receipt_proofs=bad_proofs,
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.receipt_checkpoint_valid


def test_journal_proof_leaf_subject_tamper_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    proof = bundle.journal_proofs[0]
    leaf = proof.leaf
    from skeleton.shells.ai.durable_merkle import (
        DurableMerkleLeaf,
    )

    bad_leaf = replace(
        leaf,
        subject_id="bad-subject",
        leaf_hash=DurableMerkleLeaf.compute_hash(
            chain_id=leaf.chain_id,
            chain_kind=leaf.chain_kind,
            sequence=leaf.sequence,
            item_hash=leaf.item_hash,
            previous_hash=leaf.previous_hash,
            subject_id="bad-subject",
            payload_fingerprint=(
                leaf.payload_fingerprint
            ),
        ),
    )
    bad_proof = replace(
        proof,
        leaf=bad_leaf,
    )
    bad = replace(
        bundle,
        journal_proofs=(
            bad_proof,
            *bundle.journal_proofs[1:],
        ),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.journal_proofs_valid


def test_receipt_proof_payload_tamper_rejected():
    fixture = Fixture()
    bundle = fixture.build()
    proof = bundle.receipt_proofs[0]
    leaf = proof.leaf
    from skeleton.shells.ai.durable_merkle import (
        DurableMerkleLeaf,
    )

    bad_leaf = replace(
        leaf,
        payload_fingerprint=fp("f"),
        leaf_hash=DurableMerkleLeaf.compute_hash(
            chain_id=leaf.chain_id,
            chain_kind=leaf.chain_kind,
            sequence=leaf.sequence,
            item_hash=leaf.item_hash,
            previous_hash=leaf.previous_hash,
            subject_id=leaf.subject_id,
            payload_fingerprint=fp("f"),
        ),
    )
    bad = replace(
        bundle,
        receipt_proofs=(
            replace(
                proof,
                leaf=bad_leaf,
            ),
            *bundle.receipt_proofs[1:],
        ),
    )
    report = fixture.authority.inspect(
        bad,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    assert not report.ok
    assert not report.receipt_proofs_valid


def test_wrong_journal_chain_rejected_when_chain_is_supplied():
    fixture = Fixture()
    bundle = fixture.build()
    other = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        namespace="other",
        clock=lambda: 1.0,
    )
    other.append(
        "other",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    report = fixture.authority.inspect(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=other,
        receipt_chain=fixture.receipts,
    )
    assert not report.ok
    assert not report.journal_checkpoint_valid


def test_wrong_receipt_chain_rejected_when_chain_is_supplied():
    fixture = Fixture()
    bundle = fixture.build()
    other = DistributedReceiptChain(
        InMemoryFencedStore(),
        namespace="other",
    )
    other.append(
        receipt(
            "one",
            fingerprint=fp("a"),
        )
    )
    report = fixture.authority.inspect(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=other,
    )
    assert not report.ok
    assert not report.receipt_checkpoint_valid


def test_recovery_journal_root_substitution_prevents_build():
    fixture = Fixture()
    bad_checkpoint = replace(
        fixture.recovery.session,
        journal_root=fp("f"),
    )
    bad_recovery = replace(
        fixture.recovery,
        session=bad_checkpoint,
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="journal root",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=bad_recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_recovery_receipt_root_substitution_prevents_build():
    fixture = Fixture()
    bad_checkpoint = replace(
        fixture.recovery.session,
        receipt_root=fp("f"),
    )
    bad_recovery = replace(
        fixture.recovery,
        session=bad_checkpoint,
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="receipt root",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=bad_recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_recovery_integrity_digest_substitution_prevents_build():
    fixture = Fixture()
    bad_recovery = replace(
        fixture.recovery,
        session_integrity_digest=fp("f"),
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="integrity digest",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=bad_recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_recovery_session_evidence_digest_substitution_prevents_build():
    fixture = Fixture()
    bad_recovery = replace(
        fixture.recovery,
        session_evidence_digest=fp("f"),
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="session evidence digest",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=bad_recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_recovery_session_journal_digest_substitution_prevents_build():
    fixture = Fixture()
    bad_recovery = replace(
        fixture.recovery,
        session_journal_digest=fp("f"),
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="session journal digest",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=bad_recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_invalid_integrity_report_prevents_build():
    fixture = Fixture()
    bad = replace(
        fixture.integrity,
        issues=("bad",),
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="integrity",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=fixture.recovery,
            integrity=bad,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_wrong_session_journal_identity_prevents_build():
    fixture = Fixture()
    bad = replace(
        fixture.session_journal,
        session_id="other",
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="identity mismatch",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=fixture.recovery,
            integrity=fixture.integrity,
            session_journal=bad,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_wrong_session_evidence_identity_prevents_build():
    fixture = Fixture()
    bad = replace(
        fixture.session_evidence,
        session_id="other",
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="identity mismatch",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=fixture.recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=bad,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_bundle_digest_is_stable():
    fixture = Fixture()
    first = fixture.build()
    second = fixture.build()
    assert first.digest == second.digest
    assert first == second


def test_bundle_digest_changes_with_finalization_id():
    fixture = Fixture()
    first = fixture.build()
    second = replace(
        first,
        finalization_id="other",
    )
    assert first.digest != second.digest


def test_bundle_to_dict_is_json_shaped():
    fixture = Fixture()
    bundle = fixture.build()
    data = bundle.to_dict()
    assert data["schema_version"] == 1
    assert data["finalization_id"] == "finalization"
    assert data["session_id"] == "session"
    assert len(data["journal_proofs"]) == 3
    assert len(data["receipt_proofs"]) == 2
    assert len(data["digest"]) == 64


def test_verification_to_dict_is_json_shaped():
    fixture = Fixture()
    bundle = fixture.build()
    report = fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
    )
    data = report.to_dict()
    assert data["ok"] is True
    assert data["journal_proof_count"] == 3
    assert data["receipt_proof_count"] == 2
    assert data["issues"] == []


def test_require_raises_first_issue():
    fixture = Fixture()
    bundle = fixture.build()
    with pytest.raises(
        DurableSessionMerkleError,
        match="identity",
    ):
        fixture.authority.require(
            bundle,
            finalization_id="other",
            session_id="session",
            recovery=fixture.recovery,
            integrity=fixture.integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
        )


def test_authority_requires_merkle_authority():
    with pytest.raises(
        TypeError,
        match="DurableMerkleAuthority",
    ):
        DurableSessionMerkleAuthority(
            object()
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("journal_chain_id", ""),
        ("receipt_chain_id", ""),
    ],
)
def test_authority_chain_identity_validation(field, value):
    kwargs = {
        "merkle": merkle_authority(),
        "journal_chain_id": "journal",
        "receipt_chain_id": "receipts",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        DurableSessionMerkleAuthority(
            **kwargs
        )


def test_bundle_requires_journal_proofs():
    fixture = Fixture()
    bundle = fixture.build()
    with pytest.raises(
        ValueError,
        match="requires journal proofs",
    ):
        replace(
            bundle,
            journal_proofs=(),
        )


def test_receipt_proofs_require_checkpoint():
    fixture = Fixture()
    bundle = fixture.build()
    with pytest.raises(
        ValueError,
        match="require receipt checkpoint",
    ):
        replace(
            bundle,
            receipt_checkpoint=None,
        )


def test_receipt_checkpoint_root_must_match_bundle_root():
    fixture = Fixture()
    bundle = fixture.build()
    checkpoint = replace(
        bundle.receipt_checkpoint.checkpoint,
        chain_root=fp("f"),
    )
    signature = fixture.authority.merkle.signer.sign(
        bundle.receipt_checkpoint.signature.artifact_type,
        checkpoint.digest,
        metadata={},
    )
    bad_checkpoint = replace(
        bundle.receipt_checkpoint,
        checkpoint=checkpoint,
        signature=signature,
    )
    with pytest.raises(
        ValueError,
        match="root differs",
    ):
        replace(
            bundle,
            receipt_checkpoint=bad_checkpoint,
        )


def test_journal_checkpoint_kind_must_be_journal():
    fixture = Fixture()
    bundle = fixture.build()
    wrong = replace(
        bundle.journal_checkpoint.checkpoint,
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    signature = fixture.authority.merkle.signer.sign(
        bundle.journal_checkpoint.signature.artifact_type,
        wrong.digest,
        metadata={},
    )
    bad_checkpoint = replace(
        bundle.journal_checkpoint,
        checkpoint=wrong,
        signature=signature,
    )
    bad_proofs = tuple(
        replace(
            proof,
            chain_kind=DurableMerkleChainKind.RECEIPTS,
            leaf=replace(
                proof.leaf,
                chain_kind=DurableMerkleChainKind.RECEIPTS,
                leaf_hash=proof.leaf.compute_hash(
                    chain_id=proof.leaf.chain_id,
                    chain_kind=DurableMerkleChainKind.RECEIPTS,
                    sequence=proof.leaf.sequence,
                    item_hash=proof.leaf.item_hash,
                    previous_hash=proof.leaf.previous_hash,
                    subject_id=proof.leaf.subject_id,
                    payload_fingerprint=proof.leaf.payload_fingerprint,
                ),
            ),
            checkpoint_digest=bad_checkpoint.digest,
        )
        for proof in bundle.journal_proofs
    )
    with pytest.raises(
        ValueError,
        match="wrong chain kind",
    ):
        replace(
            bundle,
            journal_checkpoint=bad_checkpoint,
            journal_proofs=bad_proofs,
        )


def test_receipt_expected_rejects_invalid_integrity_inclusion():
    fixture = Fixture()
    bad_inclusion = replace(
        fixture.integrity.receipt_inclusions[0],
        valid=False,
        reason="bad",
    )
    bad_integrity = replace(
        fixture.integrity,
        receipt_inclusions=(
            bad_inclusion,
            *fixture.integrity.receipt_inclusions[1:],
        ),
        issues=("bad",),
    )
    with pytest.raises(
        DurableSessionMerkleError,
        match="integrity",
    ):
        fixture.authority.build(
            finalization_id="finalization",
            session_id="session",
            recovery=fixture.recovery,
            integrity=bad_integrity,
            session_journal=fixture.session_journal,
            session_evidence=fixture.session_evidence,
            journal_chain=fixture.journal,
            receipt_chain=fixture.receipts,
        )


def test_many_session_events_bundle():
    fixture = Fixture(
        journal_events=25
    )
    bundle = fixture.build()
    assert len(bundle.journal_proofs) == 25
    assert fixture.authority.require(
        bundle,
        finalization_id="finalization",
        session_id="session",
        recovery=fixture.recovery,
        integrity=fixture.integrity,
        session_journal=fixture.session_journal,
        session_evidence=fixture.session_evidence,
        journal_chain=fixture.journal,
        receipt_chain=fixture.receipts,
    ).ok


def test_proof_count_is_session_scoped_not_global():
    fixture = Fixture(
        journal_events=10
    )
    for index in range(20):
        fixture.journal.append(
            f"later.{index}",
            session_id="other-later",
            intent_id="other-later",
        )
    bundle = fixture.build()
    assert len(bundle.journal_proofs) == 10
    assert fixture.journal.length() > 10


def test_bundle_historical_roots_are_exact_recovery_roots():
    fixture = Fixture()
    bundle = fixture.build()
    assert (
        bundle.journal_chain_root
        == fixture.recovery.session.journal_root
    )
    assert (
        bundle.receipt_chain_root
        == fixture.recovery.session.receipt_root
    )
