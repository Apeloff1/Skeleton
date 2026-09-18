"""Execution evidence finalization integration tests."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
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


def provenance(session, proposal, receipt_root):
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
    )


def execution_bundle(session, proposal, receipts):
    reviewed = SimpleNamespace(
        planning=SimpleNamespace(
            response=SimpleNamespace(proposal=proposal),
        )
    )
    return SimpleNamespace(
        review=reviewed,
        report=report(),
        provenance=provenance(session, proposal, receipts.root_hash()),
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
