"""Finalization-driven durable Merkle operator tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_merkle import DurableMerkleAuthority
from skeleton.shells.ai.durable_merkle_operator import (
    DurableMerkleOperatorError,
    DurableMerkleOperatorStatus,
    DurableSessionMerkleOperator,
)
from skeleton.shells.ai.durable_merkle_session import DurableSessionMerkleAuthority
from skeleton.shells.ai.durable_merkle_store import (
    DurableMerkleBundleIndex,
    DurableSessionMerkleBundleStore,
)
from skeleton.shells.ai.durable_recovery import DurableSessionRecoveryVerifier
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalizationStore,
    FinalizationPhase,
)
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.recovery_store import AIRecoveryCheckpointStore
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
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


class OperatorFixture:
    def __init__(self):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            clock=lambda: 10.0,
        )
        self.journal.append(
            "planned",
            session_id="session",
            intent_id="intent",
            proposal_id="proposal",
        )
        self.journal.append(
            "reviewed",
            session_id="session",
            intent_id="intent",
            proposal_id="proposal",
        )
        self.journal.append(
            "unrelated",
            session_id="other",
            intent_id="other",
            proposal_id="other",
        )
        self.journal.append(
            "complete",
            session_id="session",
            intent_id="intent",
            proposal_id="proposal",
        )

        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
        )
        self.receipt = ExecutionReceipt(
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
        self.receipts.append(
            self.receipt
        )

        self.session_journal = SessionJournalEvidence.from_journal(
            self.journal,
            "session",
        )
        self.execution_evidence = SessionExecutionEvidence(
            1,
            "session",
            "plan",
            fp("p"),
            True,
            (
                SessionReceiptEvidence(
                    "step",
                    "corr",
                    (
                        self.receipt.receipt_id,
                    ),
                    (
                        self.receipt.fingerprint,
                    ),
                    (
                        self.receipt.returncode,
                    ),
                    1,
                    True,
                ),
            ),
        )
        self.integrity = SessionEvidenceIntegrityVerifier(
            self.journal,
            self.receipts,
        ).require(
            self.session_journal,
            self.execution_evidence,
        )
        self.checkpoint = AISessionCheckpoint(
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
        self.recovery_checkpoint = AIRecoveryCheckpoint.wrap(
            self.checkpoint,
            session_evidence_digest=self.execution_evidence.digest,
            session_journal_digest=self.session_journal.digest,
            release_evidence_digest=fp("l"),
            runtime_trust_digest=fp("u"),
            authority_health_policy_digest=fp("h"),
            session_integrity_digest=self.integrity.digest,
        )

        self.finalizations = AIExecutionFinalizationStore(
            self.backend,
            namespace="finalizations",
            clock=lambda: 10.0,
        )
        self.recovery_store = AIRecoveryCheckpointStore(
            self.backend,
            namespace="recovery",
            clock=lambda: 10.0,
        )
        self.session_store = SessionEvidenceStore(
            self.backend,
            namespace="session-evidence",
        )
        self.session_store.put(
            self.execution_evidence
        )
        self.finalization = self.finalizations.reserve(
            session_id="session",
            provenance_digest=fp("v"),
            runtime_trust_digest=fp("u"),
            release_evidence_digest=fp("l"),
            require_recovery_checkpoint=True,
            finalization_id="finalization",
        ).finalization
        self.recovery_store.put(
            "finalization",
            self.recovery_checkpoint,
        )
        self.finalization = self.finalizations.advance(
            self.finalization,
            FinalizationPhase.SESSION_EVIDENCE,
            session_evidence_digest=self.execution_evidence.digest,
        ).finalization
        self.finalization = self.finalizations.advance(
            self.finalization,
            FinalizationPhase.CHECKPOINTED,
            session_evidence_digest=self.execution_evidence.digest,
            recovery_checkpoint_digest=self.recovery_checkpoint.digest,
        ).finalization
        self.finalization = self.finalizations.advance(
            self.finalization,
            FinalizationPhase.ANCHORED,
            session_evidence_digest=self.execution_evidence.digest,
            recovery_checkpoint_digest=self.recovery_checkpoint.digest,
            audit_anchor_digest=fp("a"),
            audit_chain_node_hash=fp("n"),
            audit_root=fp("r"),
        ).finalization
        self.finalization = self.finalizations.advance(
            self.finalization,
            FinalizationPhase.COMPLETE,
            session_evidence_digest=self.execution_evidence.digest,
            recovery_checkpoint_digest=self.recovery_checkpoint.digest,
            audit_anchor_digest=fp("a"),
            audit_chain_node_hash=fp("n"),
            audit_root=fp("r"),
        ).finalization

        self.recovery_verifier = DurableSessionRecoveryVerifier(
            finalizations=self.finalizations,
            recovery_checkpoints=self.recovery_store,
            session_evidence=self.session_store,
            journal=self.journal,
            receipt_chain=self.receipts,
            execution_evidence=None,
        )
        self.bundle_store = DurableSessionMerkleBundleStore(
            self.backend,
            namespace="merkle-bundles",
        )
        self.merkle_authority = DurableSessionMerkleAuthority(
            DurableMerkleAuthority(
                ArtifactSigner(
                    "merkle",
                    b"k" * 32,
                    clock=lambda: 100.0,
                )
            ),
            journal_chain_id="journal-main",
            receipt_chain_id="receipts-main",
        )
        self.operator = DurableSessionMerkleOperator(
            finalizations=self.finalizations,
            recovery_checkpoints=self.recovery_store,
            session_evidence=self.session_store,
            journal=self.journal,
            receipt_chain=self.receipts,
            recovery_verifier=self.recovery_verifier,
            merkle_authority=self.merkle_authority,
            bundle_store=self.bundle_store,
        )


def test_inspect_before_prepare_reports_missing():
    fixture = OperatorFixture()
    report = fixture.operator.inspect(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.MISSING
    assert not report.ok
    assert report.bundle_digest == ""
    assert report.bundle_revision is None
    assert report.journal_proof_count == 0
    assert report.receipt_proof_count == 0


def test_prepare_builds_stores_and_verifies_bundle():
    fixture = OperatorFixture()
    report = fixture.operator.prepare(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.VERIFIED
    assert report.ok
    assert report.bundle_created
    assert report.index_created
    assert report.bundle_revision == 1
    assert len(report.bundle_digest) == 64
    assert report.journal_proof_count == 3
    assert report.receipt_proof_count == 1
    assert report.verification is not None
    assert report.verification.ok


def test_prepare_is_idempotent():
    fixture = OperatorFixture()
    first = fixture.operator.prepare(
        "finalization"
    )
    second = fixture.operator.prepare(
        "finalization"
    )
    assert first.bundle_digest == second.bundle_digest
    assert not second.bundle_created
    assert not second.index_created
    assert second.ok


def test_inspect_after_prepare_verifies_existing_bundle():
    fixture = OperatorFixture()
    prepared = fixture.operator.prepare(
        "finalization"
    )
    inspected = fixture.operator.inspect(
        "finalization"
    )
    assert inspected.ok
    assert inspected.bundle_digest == prepared.bundle_digest
    assert not inspected.bundle_created
    assert not inspected.index_created


def test_verify_stored():
    fixture = OperatorFixture()
    fixture.operator.prepare(
        "finalization"
    )
    report = fixture.operator.verify_stored(
        "finalization"
    )
    assert report.ok
    assert report.status is DurableMerkleOperatorStatus.VERIFIED


def test_require_existing():
    fixture = OperatorFixture()
    fixture.operator.prepare(
        "finalization"
    )
    report = fixture.operator.require(
        "finalization"
    )
    assert report.ok


def test_require_missing_without_prepare_raises():
    fixture = OperatorFixture()
    with pytest.raises(
        DurableMerkleOperatorError,
        match="not been prepared",
    ):
        fixture.operator.require(
            "finalization"
        )


def test_require_missing_with_prepare_builds_bundle():
    fixture = OperatorFixture()
    report = fixture.operator.require(
        "finalization",
        prepare_if_missing=True,
    )
    assert report.ok
    assert report.bundle_created
    assert report.index_created


def test_prepare_if_missing_must_be_bool():
    fixture = OperatorFixture()
    with pytest.raises(
        ValueError,
        match="bool",
    ):
        fixture.operator.require(
            "finalization",
            prepare_if_missing="yes",
        )


def test_later_journal_growth_keeps_stored_bundle_verified():
    fixture = OperatorFixture()
    prepared = fixture.operator.prepare(
        "finalization"
    )
    fixture.journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    report = fixture.operator.verify_stored(
        "finalization"
    )
    assert report.ok
    assert report.bundle_digest == prepared.bundle_digest


def test_later_receipt_growth_keeps_stored_bundle_verified():
    fixture = OperatorFixture()
    prepared = fixture.operator.prepare(
        "finalization"
    )
    fixture.receipts.append(
        ExecutionReceipt(
            command="python",
            correlation_id="later",
            fingerprint=fp("f"),
            started_at="2026-09-19T00:00:00+00:00",
            finished_at="2026-09-19T00:00:01+00:00",
            duration_ms=1.0,
            returncode=0,
            ok=True,
            timed_out=False,
            output_limited=False,
            stdout_bytes=0,
            stderr_bytes=0,
            attempt=1,
            receipt_id="later-receipt",
        )
    )
    report = fixture.operator.verify_stored(
        "finalization"
    )
    assert report.ok
    assert report.bundle_digest == prepared.bundle_digest


def test_later_growth_on_both_chains_keeps_bundle_verified():
    fixture = OperatorFixture()
    prepared = fixture.operator.prepare(
        "finalization"
    )
    fixture.journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    fixture.receipts.append(
        ExecutionReceipt(
            command="python",
            correlation_id="later",
            fingerprint=fp("f"),
            started_at="2026-09-19T00:00:00+00:00",
            finished_at="2026-09-19T00:00:01+00:00",
            duration_ms=1.0,
            returncode=0,
            ok=True,
            timed_out=False,
            output_limited=False,
            stdout_bytes=0,
            stderr_bytes=0,
            attempt=1,
            receipt_id="later-receipt",
        )
    )
    assert fixture.operator.verify_stored(
        "finalization"
    ).bundle_digest == prepared.bundle_digest


def test_missing_finalization_reports_incomplete():
    fixture = OperatorFixture()
    report = fixture.operator.inspect(
        "missing-finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.INCOMPLETE
    assert report.safe_to_resume
    assert not report.ok


def test_missing_recovery_checkpoint_reports_incomplete():
    fixture = OperatorFixture()
    key = fixture.recovery_store._item_key(
        "finalization"
    )
    record = fixture.backend.get(
        fixture.recovery_store.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.recovery_store.namespace,
        key,
        expected_revision=record.revision,
    )
    report = fixture.operator.inspect(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.INCOMPLETE
    assert report.safe_to_resume


def test_conflicting_session_evidence_reports_manual_review():
    fixture = OperatorFixture()
    record = fixture.backend.get(
        fixture.session_store.namespace,
        "session",
    )
    fixture.backend.compare_and_swap(
        fixture.session_store.namespace,
        "session",
        expected_revision=record.revision,
        value=replace(
            record.value,
            plan_fingerprint=fp("f"),
        ),
    )
    report = fixture.operator.inspect(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.MANUAL_REVIEW
    assert report.requires_manual_review
    assert not report.ok


def test_prepare_does_not_build_on_incomplete_recovery():
    fixture = OperatorFixture()
    key = fixture.recovery_store._item_key(
        "finalization"
    )
    record = fixture.backend.get(
        fixture.recovery_store.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.recovery_store.namespace,
        key,
        expected_revision=record.revision,
    )
    report = fixture.operator.prepare(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.INCOMPLETE
    assert (
        fixture.bundle_store
        .get_by_finalization(
            "finalization"
        )
        is None
    )


def test_prepare_does_not_build_on_manual_review():
    fixture = OperatorFixture()
    record = fixture.backend.get(
        fixture.session_store.namespace,
        "session",
    )
    fixture.backend.compare_and_swap(
        fixture.session_store.namespace,
        "session",
        expected_revision=record.revision,
        value=replace(
            record.value,
            plan_fingerprint=fp("f"),
        ),
    )
    report = fixture.operator.prepare(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.MANUAL_REVIEW
    assert (
        fixture.bundle_store
        .get_by_finalization(
            "finalization"
        )
        is None
    )


def test_corrupt_bundle_index_reports_manual_review():
    fixture = OperatorFixture()
    prepared = fixture.operator.prepare(
        "finalization"
    )
    key = fixture.bundle_store._finalization_key(
        "finalization"
    )
    record = fixture.backend.get(
        fixture.bundle_store.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.bundle_store.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            session_integrity_digest=fp("f"),
        ),
    )
    report = fixture.operator.inspect(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.MANUAL_REVIEW
    assert report.requires_manual_review
    assert not report.ok
    assert report.bundle_digest == ""


def test_missing_bundle_behind_existing_index_reports_manual_review():
    fixture = OperatorFixture()
    fixture.operator.prepare(
        "finalization"
    )
    index = fixture.bundle_store.index(
        "finalization"
    )
    key = fixture.bundle_store._bundle_key(
        index.index.bundle_digest
    )
    record = fixture.backend.get(
        fixture.bundle_store.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.bundle_store.namespace,
        key,
        expected_revision=record.revision,
    )
    report = fixture.operator.inspect(
        "finalization"
    )
    assert report.status is DurableMerkleOperatorStatus.MANUAL_REVIEW


def test_verify_stored_missing_raises():
    fixture = OperatorFixture()
    with pytest.raises(
        DurableMerkleOperatorError,
        match="missing",
    ):
        fixture.operator.verify_stored(
            "finalization"
        )


def test_operator_result_to_dict():
    fixture = OperatorFixture()
    report = fixture.operator.prepare(
        "finalization"
    )
    data = report.to_dict()
    assert data["status"] == "verified"
    assert data["ok"] is True
    assert data["safe_to_resume"] is False
    assert data["requires_manual_review"] is False
    assert data["bundle_digest"] == report.bundle_digest
    assert data["verification"]["ok"] is True


def test_operator_result_missing_to_dict():
    fixture = OperatorFixture()
    report = fixture.operator.inspect(
        "finalization"
    )
    data = report.to_dict()
    assert data["status"] == "missing"
    assert data["ok"] is False
    assert data["bundle_revision"] is None
    assert data["verification"] is None


def test_operator_constructor_validates_finalization_store():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="finalizations",
    ):
        DurableSessionMerkleOperator(
            finalizations=object(),
            recovery_checkpoints=fixture.recovery_store,
            session_evidence=fixture.session_store,
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            recovery_verifier=fixture.recovery_verifier,
            merkle_authority=fixture.merkle_authority,
            bundle_store=fixture.bundle_store,
        )


def test_operator_constructor_validates_recovery_store():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="recovery_checkpoints",
    ):
        DurableSessionMerkleOperator(
            finalizations=fixture.finalizations,
            recovery_checkpoints=object(),
            session_evidence=fixture.session_store,
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            recovery_verifier=fixture.recovery_verifier,
            merkle_authority=fixture.merkle_authority,
            bundle_store=fixture.bundle_store,
        )


def test_operator_constructor_validates_session_store():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="session_evidence",
    ):
        DurableSessionMerkleOperator(
            finalizations=fixture.finalizations,
            recovery_checkpoints=fixture.recovery_store,
            session_evidence=object(),
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            recovery_verifier=fixture.recovery_verifier,
            merkle_authority=fixture.merkle_authority,
            bundle_store=fixture.bundle_store,
        )


def test_operator_constructor_validates_recovery_verifier():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="recovery_verifier",
    ):
        DurableSessionMerkleOperator(
            finalizations=fixture.finalizations,
            recovery_checkpoints=fixture.recovery_store,
            session_evidence=fixture.session_store,
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            recovery_verifier=object(),
            merkle_authority=fixture.merkle_authority,
            bundle_store=fixture.bundle_store,
        )


def test_operator_constructor_validates_merkle_authority():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="merkle_authority",
    ):
        DurableSessionMerkleOperator(
            finalizations=fixture.finalizations,
            recovery_checkpoints=fixture.recovery_store,
            session_evidence=fixture.session_store,
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            recovery_verifier=fixture.recovery_verifier,
            merkle_authority=object(),
            bundle_store=fixture.bundle_store,
        )


def test_operator_constructor_validates_bundle_store():
    fixture = OperatorFixture()
    with pytest.raises(
        TypeError,
        match="bundle_store",
    ):
        DurableSessionMerkleOperator(
            finalizations=fixture.finalizations,
            recovery_checkpoints=fixture.recovery_store,
            session_evidence=fixture.session_store,
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            recovery_verifier=fixture.recovery_verifier,
            merkle_authority=fixture.merkle_authority,
            bundle_store=object(),
        )


def test_fresh_operator_instance_reuses_stored_bundle():
    fixture = OperatorFixture()
    prepared = fixture.operator.prepare(
        "finalization"
    )
    fresh = DurableSessionMerkleOperator(
        finalizations=fixture.finalizations,
        recovery_checkpoints=fixture.recovery_store,
        session_evidence=fixture.session_store,
        journal=fixture.journal,
        receipt_chain=fixture.receipts,
        recovery_verifier=DurableSessionRecoveryVerifier(
            finalizations=fixture.finalizations,
            recovery_checkpoints=fixture.recovery_store,
            session_evidence=fixture.session_store,
            journal=fixture.journal,
            receipt_chain=fixture.receipts,
            execution_evidence=None,
        ),
        merkle_authority=fixture.merkle_authority,
        bundle_store=DurableSessionMerkleBundleStore(
            fixture.backend,
            namespace="merkle-bundles",
        ),
    )
    report = fresh.verify_stored(
        "finalization"
    )
    assert report.ok
    assert report.bundle_digest == prepared.bundle_digest


def test_prepare_after_later_chain_growth_reuses_same_bundle():
    fixture = OperatorFixture()
    first = fixture.operator.prepare(
        "finalization"
    )
    fixture.journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    fixture.receipts.append(
        ExecutionReceipt(
            command="python",
            correlation_id="later",
            fingerprint=fp("f"),
            started_at="2026-09-19T00:00:00+00:00",
            finished_at="2026-09-19T00:00:01+00:00",
            duration_ms=1.0,
            returncode=0,
            ok=True,
            timed_out=False,
            output_limited=False,
            stdout_bytes=0,
            stderr_bytes=0,
            attempt=1,
            receipt_id="later",
        )
    )
    second = fixture.operator.prepare(
        "finalization"
    )
    assert second.ok
    assert second.bundle_digest == first.bundle_digest
    assert not second.bundle_created
    assert not second.index_created


def test_prepare_generates_session_scoped_proof_counts():
    fixture = OperatorFixture()
    report = fixture.operator.prepare(
        "finalization"
    )
    assert report.journal_proof_count == len(
        fixture.session_journal.events
    )
    assert report.receipt_proof_count == len(
        fixture.integrity.receipt_inclusions
    )


def test_recovery_report_digest_is_stable_across_prepare():
    fixture = OperatorFixture()
    before = fixture.recovery_verifier.require_verified(
        "finalization"
    ).digest
    prepared = fixture.operator.prepare(
        "finalization"
    )
    after = fixture.recovery_verifier.require_verified(
        "finalization"
    ).digest
    assert before == after
    assert prepared.recovery_report_digest == before
