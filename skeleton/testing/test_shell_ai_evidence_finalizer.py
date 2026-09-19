"""Execution evidence finalization integration tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore
from skeleton.shells.ai.audit_witness import AIAuditWitnessStore
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceBuilder, AIExecutionEvidenceStore
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.provenance import AIDecisionProvenance
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.session_evidence import SessionEvidenceStore
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.plan_executor import PlanExecutionReport, StepExecution, StepState
from skeleton.shells.receipts import ReceiptChain


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def completed_session():
    intent = AIIntent("intent", "complete a test plan")
    proposal = AIPlanProposal(
        "proposal",
        intent.intent_id,
        (AIAction("step", "python", ("-V",)),),
        confidence=0.9,
        uncertainty=0.1,
        model_id="model",
    )
    session = AIShellSession("session", intent, clock=lambda: 1.0)
    session.transition(AISessionPhase.PLANNING)
    session.set_proposal(proposal)
    session.transition(AISessionPhase.REVIEW)
    session.transition(AISessionPhase.APPROVED)
    session.transition(AISessionPhase.EXECUTING)
    session.transition(AISessionPhase.VERIFYING)
    session.transition(AISessionPhase.COMPLETE)
    return session, proposal


def report():
    return PlanExecutionReport(
        "plan",
        fp("x"),
        (
            StepExecution(
                "step",
                StepState.SUCCEEDED,
                None,
                "",
                1.0,
                2.0,
            ),
        ),
        1.0,
        2.0,
    )


def provenance(
    session,
    proposal,
    receipt_root,
    *,
    runtime_trust_digest="",
    authority_health_policy_digest="",
):
    return AIDecisionProvenance(
        intent_fingerprint=session.intent.fingerprint,
        proposal_fingerprint=proposal.fingerprint,
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        policy_fingerprint=fp("p"),
        schema_digest=fp("s"),
        model_id="model",
        risk_score=5,
        receipt_root=receipt_root,
        execution_backend_id="shell-service-host",
        release_evidence_digest=fp("l"),
        runtime_trust_digest=runtime_trust_digest,
        authority_health_policy_digest=authority_health_policy_digest,
    )


def execution_bundle(
    session,
    proposal,
    receipts,
    *,
    runtime_trust_digest="",
    authority_health_policy_digest="",
):
    reviewed = SimpleNamespace(
        planning=SimpleNamespace(
            response=SimpleNamespace(proposal=proposal),
        )
    )
    return SimpleNamespace(
        review=reviewed,
        report=report(),
        provenance=provenance(
            session,
            proposal,
            receipts.root_hash(),
            runtime_trust_digest=runtime_trust_digest,
            authority_health_policy_digest=authority_health_policy_digest,
        ),
    )


def environment():
    backend = InMemoryFencedStore()
    journal = AIDecisionJournal(clock=lambda: 10.0)
    receipts = ReceiptChain()
    evidence = SessionEvidenceStore(
        backend,
        namespace="session-evidence",
    )
    anchors = AIAuditAnchorStore(
        backend,
        ArtifactSigner("audit", b"k" * 32, clock=lambda: 10.0),
        namespace="audit",
        clock=lambda: 10.0,
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=evidence,
        audit_anchors=anchors,
    )
    return journal, receipts, evidence, anchors, finalizer


def test_finalizer_commits_recovery_and_signed_audit_evidence():
    session, proposal = completed_session()
    journal, receipts, evidence, anchors, finalizer = environment()
    journal.append(
        "ai.plan.completed",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
    )
    assert result.checkpoint.session_id == "session"
    assert result.recovery_checkpoint.session_evidence_digest == result.session_evidence.digest
    assert result.recovery_checkpoint.session_journal_digest == result.session_journal.digest
    assert result.recovery_checkpoint.release_evidence_digest == fp("l")
    assert evidence.current("session").evidence.digest == result.session_evidence.digest
    assert anchors.verify()
    assert result.audit_anchor.anchor.checkpoint_digest == result.recovery_checkpoint.digest
    assert result.audit_anchor.anchor.provenance_digest == bundle.provenance.digest


def test_finalizer_evidence_survives_fresh_store_reader():
    session, proposal = completed_session()
    journal, receipts, evidence, anchors, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    result = finalizer.finalize(
        session,
        execution_bundle(session, proposal, receipts),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
    )
    assert anchors.snapshot()[0].anchor.session_id == session.session_id
    assert anchors.snapshot()[0].anchor.session_evidence_digest == result.session_evidence.digest


def test_finalizer_rejects_nonterminal_session():
    session, proposal = completed_session()
    session._phase = AISessionPhase.VERIFYING
    _, receipts, _, _, finalizer = environment()
    with pytest.raises(RuntimeError, match="completed attempt"):
        finalizer.finalize(
            session,
            execution_bundle(session, proposal, receipts),
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
        )


def test_finalizer_rejects_foreign_proposal():
    session, proposal = completed_session()
    _, receipts, _, _, finalizer = environment()
    foreign = AIPlanProposal(
        "other",
        session.intent.intent_id,
        proposal.actions,
        confidence=proposal.confidence,
        uncertainty=proposal.uncertainty,
        model_id=proposal.model_id,
    )
    bundle = execution_bundle(session, foreign, receipts)
    with pytest.raises(RuntimeError, match="does not belong"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
        )


@pytest.mark.parametrize(
    "field,value,phrase",
    [
        ("policy_fingerprint", fp("q"), "policy"),
        ("tool_catalog_digest", fp("u"), "tool catalog"),
        ("effect_digest", fp("f"), "effect registry"),
    ],
)
def test_finalizer_rejects_control_surface_mismatch(field, value, phrase):
    session, proposal = completed_session()
    _, receipts, _, _, finalizer = environment()
    bundle = execution_bundle(session, proposal, receipts)
    kwargs = {
        "policy_fingerprint": fp("p"),
        "tool_catalog_digest": fp("t"),
        "effect_digest": fp("e"),
    }
    kwargs[field] = value
    with pytest.raises(RuntimeError, match=phrase):
        finalizer.finalize(session, bundle, **kwargs)


def test_finalizer_rejects_release_mismatch():
    session, proposal = completed_session()
    _, receipts, _, _, finalizer = environment()
    bundle = execution_bundle(session, proposal, receipts)
    with pytest.raises(RuntimeError, match="release evidence"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("z"),
        )


def test_finalizer_rejects_corrupt_journal():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    bundle = execution_bundle(session, proposal, receipts)

    class CorruptJournal:
        def verify(self):
            return False

    finalizer.journal = CorruptJournal()
    with pytest.raises(RuntimeError, match="journal"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
        )


def test_finalizer_rejects_corrupt_receipt_chain():
    session, proposal = completed_session()
    _, receipts, _, _, finalizer = environment()
    bundle = execution_bundle(session, proposal, receipts)

    class CorruptReceipts:
        def verify(self):
            return False

    finalizer.receipt_chain = CorruptReceipts()
    with pytest.raises(RuntimeError, match="receipt chain"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
        )


def test_finalizer_accepts_stable_reconstructed_proposal_identity():
    session, proposal = completed_session()
    journal, receipts, _, anchors, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    reconstructed = AIPlanProposal(
        proposal.proposal_id,
        proposal.intent_id,
        proposal.actions,
        confidence=proposal.confidence,
        uncertainty=proposal.uncertainty,
        model_id=proposal.model_id,
    )
    bundle = execution_bundle(session, reconstructed, receipts)
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
    )
    assert anchors.verify()
    assert result.audit_anchor.anchor.provenance_digest == bundle.provenance.digest


def test_finalizer_can_emit_signed_top_level_execution_evidence():
    session, proposal = completed_session()
    backend = InMemoryFencedStore()
    journal = AIDecisionJournal(clock=lambda: 10.0)
    receipts = ReceiptChain()
    session_store = SessionEvidenceStore(
        backend,
        namespace="session-evidence",
    )
    audit_store = AIAuditAnchorStore(
        backend,
        ArtifactSigner("audit", b"a" * 32, clock=lambda: 10.0),
        namespace="audit",
        clock=lambda: 10.0,
    )
    execution_store = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner("execution", b"e" * 32, clock=lambda: 10.0),
        namespace="execution-evidence",
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=session_store,
        audit_anchors=audit_store,
        execution_evidence=execution_store,
        execution_evidence_builder=AIExecutionEvidenceBuilder(
            clock=lambda: 11.0,
        ),
    )
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        model_attestation_digest=fp("m"),
        execution_seal_id="seal-1",
        quorum_approval_digest=fp("q"),
    )
    assert result.execution_evidence is not None
    signed = result.execution_evidence
    assert signed.evidence.session_id == session.session_id
    assert signed.evidence.provenance_digest == bundle.provenance.digest
    assert signed.evidence.checkpoint_digest == result.recovery_checkpoint.digest
    assert signed.evidence.session_evidence_digest == result.session_evidence.digest
    assert signed.evidence.session_journal_digest == result.session_journal.digest
    assert signed.evidence.audit_anchor_digest == result.audit_anchor.anchor.digest
    assert signed.evidence.audit_chain_node_hash == result.audit_anchor.chain_node_hash
    assert signed.evidence.release_evidence_digest == fp("l")
    assert signed.evidence.model_attestation_digest == fp("m")
    assert signed.evidence.execution_seal_id == "seal-1"
    assert signed.evidence.quorum_approval_digest == fp("q")
    assert execution_store.verify()


def test_finalizer_without_execution_store_remains_backward_compatible():
    session, proposal = completed_session()
    journal, receipts, _, anchors, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    result = finalizer.finalize(
        session,
        execution_bundle(session, proposal, receipts),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
    )
    assert result.execution_evidence is None
    assert result.to_dict()["execution_evidence"] is None
    assert anchors.verify()


def test_finalizer_publishes_rollback_witness_and_binds_trust():
    session, proposal = completed_session()
    backend = InMemoryFencedStore()
    journal = AIDecisionJournal(clock=lambda: 10.0)
    receipts = ReceiptChain()
    session_store = SessionEvidenceStore(
        backend,
        namespace="session-evidence",
    )
    audit_signer = ArtifactSigner(
        "audit",
        b"a" * 32,
        clock=lambda: 10.0,
    )
    audit_store = AIAuditAnchorStore(
        backend,
        audit_signer,
        namespace="audit",
        clock=lambda: 10.0,
    )
    witness_store = AIAuditWitnessStore(
        backend,
        audit_signer,
        namespace="audit-witness",
        clock=lambda: 10.5,
    )
    execution_store = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner(
            "execution",
            b"e" * 32,
            clock=lambda: 11.0,
        ),
        namespace="execution-evidence",
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=session_store,
        audit_anchors=audit_store,
        audit_witnesses=witness_store,
        execution_evidence=execution_store,
        execution_evidence_builder=AIExecutionEvidenceBuilder(
            clock=lambda: 12.0,
        ),
    )
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(
        session,
        proposal,
        receipts,
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
    )
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_seal_id="seal-1",
    )

    assert result.audit_witness is not None
    witness = result.audit_witness
    assert witness.witness.audit_root == audit_store.root_hash()
    assert witness.witness.runtime_trust_digest == fp("u")
    assert witness.witness.release_evidence_digest == fp("l")
    assert witness_store.verify().ok
    assert witness_store.require_current_root(
        audit_store.root_hash(),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    ) == witness

    assert result.recovery_checkpoint.runtime_trust_digest == fp("u")
    assert (
        result.recovery_checkpoint.authority_health_policy_digest
        == fp("h")
    )
    assert result.audit_anchor.anchor.runtime_trust_digest == fp("u")
    assert (
        result.audit_anchor.anchor.authority_health_policy_digest
        == fp("h")
    )

    signed = result.execution_evidence
    assert signed is not None
    assert signed.evidence.runtime_trust_digest == fp("u")
    assert signed.evidence.authority_health_policy_digest == fp("h")
    assert signed.evidence.audit_witness_digest == witness.witness.digest
    assert signed.evidence.audit_witness_sequence == witness.witness.sequence
    assert execution_store.verify()


def test_finalizer_rejects_runtime_trust_provenance_mismatch():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(
        session,
        proposal,
        receipts,
        runtime_trust_digest=fp("a"),
    )
    with pytest.raises(RuntimeError, match="runtime trust"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            runtime_trust_digest=fp("b"),
        )


def test_finalizer_rejects_authority_health_policy_provenance_mismatch():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(
        session,
        proposal,
        receipts,
        authority_health_policy_digest=fp("a"),
    )
    with pytest.raises(RuntimeError, match="authority health"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            authority_health_policy_digest=fp("b"),
        )


def test_finalizer_witness_survives_fresh_reader():
    session, proposal = completed_session()
    backend = InMemoryFencedStore()
    audit_signer = ArtifactSigner(
        "audit",
        b"a" * 32,
        clock=lambda: 5.0,
    )
    journal = AIDecisionJournal(clock=lambda: 5.0)
    receipts = ReceiptChain()
    audit_store = AIAuditAnchorStore(
        backend,
        audit_signer,
        namespace="audit",
        clock=lambda: 5.0,
    )
    witnesses = AIAuditWitnessStore(
        backend,
        audit_signer,
        namespace="witness",
        clock=lambda: 6.0,
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=SessionEvidenceStore(
            backend,
            namespace="session",
        ),
        audit_anchors=audit_store,
        audit_witnesses=witnesses,
    )
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    result = finalizer.finalize(
        session,
        execution_bundle(session, proposal, receipts),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
    )
    assert result.audit_witness is not None

    fresh = AIAuditWitnessStore(
        backend,
        ArtifactSigner(
            "audit",
            b"a" * 32,
            clock=lambda: 9.0,
        ),
        namespace="witness",
        clock=lambda: 9.0,
    )
    verification = fresh.verify()
    assert verification.ok
    assert verification.audit_root == audit_store.root_hash()
    current = fresh.require_current_root(
        audit_store.root_hash(),
        release_evidence_digest=fp("l"),
    )
    assert current.witness.digest == result.audit_witness.witness.digest


def test_finalizer_binds_execution_attempt_across_all_evidence_layers():
    session, proposal = completed_session()
    backend = InMemoryFencedStore()
    journal = AIDecisionJournal(clock=lambda: 10.0)
    receipts = ReceiptChain()
    session_store = SessionEvidenceStore(
        backend,
        namespace="session-evidence-attempt",
    )
    audit_store = AIAuditAnchorStore(
        backend,
        ArtifactSigner("audit", b"k" * 32, clock=lambda: 10.0),
        namespace="audit-attempt",
        clock=lambda: 10.0,
    )
    execution_store = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner("execution", b"x" * 32, clock=lambda: 11.0),
        namespace="execution-attempt",
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=session_store,
        audit_anchors=audit_store,
        execution_evidence=execution_store,
        execution_evidence_builder=AIExecutionEvidenceBuilder(
            clock=lambda: 12.0,
        ),
    )
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    result = finalizer.finalize(
        session,
        execution_bundle(session, proposal, receipts),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-attempt",
        execution_attempt_authority_digest=fp("a"),
    )

    recovery = result.recovery_checkpoint
    assert recovery.execution_attempt_id == "seal-attempt"
    assert recovery.execution_attempt_authority_digest == fp("a")
    anchor = result.audit_anchor.anchor
    assert anchor.execution_attempt_id == "seal-attempt"
    assert anchor.execution_attempt_authority_digest == fp("a")
    signed = result.execution_evidence
    assert signed is not None
    assert signed.evidence.execution_attempt_id == "seal-attempt"
    assert signed.evidence.execution_attempt_authority_digest == fp("a")
    assert audit_store.verify()
    assert execution_store.verify()


def test_finalizer_rejects_attempt_authority_without_execution_seal():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    with pytest.raises(RuntimeError, match="execution seal"):
        finalizer.finalize(
            session,
            execution_bundle(session, proposal, receipts),
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            execution_attempt_authority_digest=fp("a"),
        )


def test_finalizer_rejects_malformed_attempt_authority_digest():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    with pytest.raises(ValueError, match="execution_attempt_authority_digest"):
        finalizer.finalize(
            session,
            execution_bundle(session, proposal, receipts),
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            execution_seal_id="seal-attempt",
            execution_attempt_authority_digest="bad",
        )


def test_finalizer_attempt_binding_changes_recovery_digest():
    session, proposal = completed_session()
    first_journal, first_receipts, _, _, first_finalizer = environment()
    first_journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    first = first_finalizer.finalize(
        session,
        execution_bundle(session, proposal, first_receipts),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        execution_seal_id="seal-a",
        execution_attempt_authority_digest=fp("a"),
    )

    second_session, second_proposal = completed_session()
    second_journal, second_receipts, _, _, second_finalizer = environment()
    second_journal.append(
        "done",
        session_id=second_session.session_id,
        intent_id=second_session.intent.intent_id,
        proposal_id=second_proposal.proposal_id,
    )
    second = second_finalizer.finalize(
        second_session,
        execution_bundle(
            second_session,
            second_proposal,
            second_receipts,
        ),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        execution_seal_id="seal-b",
        execution_attempt_authority_digest=fp("b"),
    )
    assert first.recovery_checkpoint.digest != second.recovery_checkpoint.digest
    assert first.audit_anchor.anchor.digest != second.audit_anchor.anchor.digest


def _successful_attempt(
    bundle,
    *,
    attempt_id="seal-1",
    session_id="session",
    principal="alice",
    worker_id="worker-1",
    seal_id="seal-1",
    backend_id="shell-service-host",
    runtime_trust_digest="",
    release_evidence_digest=fp("l"),
    terminal_evidence_digest=None,
):
    return AIExecutionAttempt(
        1,
        attempt_id,
        session_id,
        principal,
        worker_id,
        bundle.report.fingerprint,
        seal_id,
        ExecutionAttemptState.SUCCEEDED,
        1.0,
        2.0,
        runtime_trust_digest=runtime_trust_digest,
        release_evidence_digest=release_evidence_digest,
        execution_backend_id=backend_id,
        terminal_evidence_digest=(
            bundle.provenance.digest
            if terminal_evidence_digest is None
            else terminal_evidence_digest
        ),
    )


def test_finalizer_binds_successful_execution_attempt_into_recovery_and_anchor():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = _successful_attempt(bundle)
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-1",
        execution_attempt=attempt,
    )
    assert result.recovery_checkpoint.execution_attempt_id == "seal-1"
    assert (
        result.recovery_checkpoint.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert result.audit_anchor.anchor.execution_attempt_id == "seal-1"
    assert (
        result.audit_anchor.anchor.execution_attempt_authority_digest
        == attempt.authority_digest
    )


def test_finalizer_attempt_runtime_trust_matches_provenance_and_argument():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(
        session,
        proposal,
        receipts,
        runtime_trust_digest=fp("u"),
    )
    attempt = _successful_attempt(
        bundle,
        runtime_trust_digest=fp("u"),
    )
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        execution_seal_id="seal-1",
        execution_attempt=attempt,
    )
    assert result.recovery_checkpoint.runtime_trust_digest == fp("u")
    assert (
        result.recovery_checkpoint.execution_attempt_authority_digest
        == attempt.authority_digest
    )


def test_finalizer_rejects_attempt_session_substitution():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = _successful_attempt(bundle, session_id="other")
    with pytest.raises(RuntimeError, match="attempt session"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_rejects_attempt_plan_substitution():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = replace(
        _successful_attempt(bundle),
        plan_fingerprint=fp("z"),
    )
    with pytest.raises(RuntimeError, match="attempt plan"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_rejects_attempt_seal_substitution():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = _successful_attempt(bundle, seal_id="different")
    with pytest.raises(RuntimeError, match="attempt seal"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_rejects_attempt_backend_substitution():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = _successful_attempt(bundle, backend_id="other")
    with pytest.raises(RuntimeError, match="attempt backend"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_rejects_attempt_runtime_trust_substitution():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(
        session,
        proposal,
        receipts,
        runtime_trust_digest=fp("u"),
    )
    attempt = _successful_attempt(
        bundle,
        runtime_trust_digest=fp("x"),
    )
    with pytest.raises(RuntimeError, match="attempt runtime trust"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            runtime_trust_digest=fp("u"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_rejects_attempt_release_substitution():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = _successful_attempt(
        bundle,
        release_evidence_digest=fp("x"),
    )
    with pytest.raises(RuntimeError, match="attempt release"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_completed_session_requires_successful_attempt():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = AIExecutionAttempt(
        1,
        "seal-1",
        session.session_id,
        "alice",
        "worker-1",
        bundle.report.fingerprint,
        "seal-1",
        ExecutionAttemptState.FAILED,
        1.0,
        2.0,
        release_evidence_digest=fp("l"),
        execution_backend_id="shell-service-host",
        terminal_evidence_digest=bundle.provenance.digest,
        error_type="SyntheticFailure",
    )
    with pytest.raises(RuntimeError, match="successful execution attempt"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_rejects_attempt_terminal_provenance_mismatch():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    attempt = _successful_attempt(
        bundle,
        terminal_evidence_digest=fp("z"),
    )
    with pytest.raises(RuntimeError, match="terminal evidence"):
        finalizer.finalize(
            session,
            bundle,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id="seal-1",
            execution_attempt=attempt,
        )


def test_finalizer_legacy_flow_without_attempt_remains_supported():
    session, proposal = completed_session()
    journal, receipts, _, _, finalizer = environment()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    bundle = execution_bundle(session, proposal, receipts)
    result = finalizer.finalize(
        session,
        bundle,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
    )
    assert result.recovery_checkpoint.execution_attempt_id == ""
    assert result.recovery_checkpoint.execution_attempt_authority_digest == ""
