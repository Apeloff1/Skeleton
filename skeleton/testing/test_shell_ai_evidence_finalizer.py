"""Execution evidence finalization integration tests."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore
from skeleton.shells.ai.audit_witness import AIAuditWitnessStore
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
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
    return char * 64


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
