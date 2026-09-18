"""Crash-recovery reconciliation tests for AI execution finalization."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore
from skeleton.shells.ai.audit_witness import AIAuditWitnessStore
from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_evidence import (
    AIExecutionEvidenceBuilder,
    AIExecutionEvidenceStore,
)
from skeleton.shells.ai.finalization_reconciler import (
    AIExecutionFinalizationReconciler,
    FinalizationReconcileAction,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalizationStore,
    ExecutionFinalizationConflict,
    FinalizationPhase,
)
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.provenance import AIDecisionProvenance
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.recovery_store import AIRecoveryCheckpointStore
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
    SessionExecutionEvidence,
)
from skeleton.shells.ai.session_journal import SessionJournalEvidence
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.evidence_chain import EvidenceNode
from skeleton.shells.plan_executor import (
    PlanExecutionReport,
    StepExecution,
    StepState,
)
from skeleton.shells.receipts import ReceiptChain


def fp(char: str) -> str:
    return char * 64


def terminal_session(
    suffix: str = "",
) -> tuple[AIShellSession, AIPlanProposal]:
    intent = AIIntent(
        f"intent{suffix}",
        f"reconcile execution {suffix}",
    )
    proposal = AIPlanProposal(
        f"proposal{suffix}",
        intent.intent_id,
        (
            AIAction(
                f"step{suffix}",
                "python",
                ("-V",),
            ),
        ),
        confidence=0.9,
        uncertainty=0.1,
        model_id="model",
    )
    session = AIShellSession(
        f"session{suffix}",
        intent,
        clock=lambda: 1.0,
    )
    session.transition(AISessionPhase.PLANNING)
    session.set_proposal(proposal)
    session.transition(AISessionPhase.REVIEW)
    session.transition(AISessionPhase.APPROVED)
    session.transition(AISessionPhase.EXECUTING)
    session.transition(AISessionPhase.VERIFYING)
    session.transition(AISessionPhase.COMPLETE)
    return session, proposal


def report(suffix: str = "") -> PlanExecutionReport:
    return PlanExecutionReport(
        f"plan{suffix}",
        fp("x" if not suffix else "y"),
        (
            StepExecution(
                f"step{suffix}",
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


def execution_bundle(
    session: AIShellSession,
    proposal: AIPlanProposal,
    receipts: ReceiptChain,
    *,
    suffix: str = "",
):
    reviewed = SimpleNamespace(
        planning=SimpleNamespace(
            response=SimpleNamespace(proposal=proposal),
        )
    )
    provenance = AIDecisionProvenance(
        intent_fingerprint=session.intent.fingerprint,
        proposal_fingerprint=proposal.fingerprint,
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        policy_fingerprint=fp("p"),
        schema_digest=fp("s"),
        model_id="model",
        risk_score=5,
        receipt_root=receipts.root_hash(),
        execution_backend_id="shell-service-host",
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
    )
    return SimpleNamespace(
        review=reviewed,
        report=report(suffix),
        provenance=provenance,
    )


def successful_attempt(
    execution,
    session,
    *,
    seal_id="seal",
) -> AIExecutionAttempt:
    return AIExecutionAttempt(
        1,
        seal_id,
        session.session_id,
        "alice",
        "worker",
        execution.report.fingerprint,
        seal_id,
        ExecutionAttemptState.SUCCEEDED,
        1.0,
        2.0,
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
        execution_backend_id="shell-service-host",
        terminal_evidence_digest=execution.provenance.digest,
    )


class Env:
    def __init__(self):
        self.backend = InMemoryFencedStore()
        self.journal = AIDecisionJournal(clock=lambda: 10.0)
        self.receipts = ReceiptChain()
        self.session_evidence = SessionEvidenceStore(
            self.backend,
            namespace="session-evidence",
        )
        self.recovery = AIRecoveryCheckpointStore(
            self.backend,
            namespace="recovery",
            clock=lambda: 10.0,
        )
        self.anchors = AIAuditAnchorStore(
            self.backend,
            ArtifactSigner(
                "audit",
                b"a" * 32,
                clock=lambda: 10.0,
            ),
            namespace="anchors",
            clock=lambda: 10.0,
        )
        self.witnesses = AIAuditWitnessStore(
            self.backend,
            ArtifactSigner(
                "witness",
                b"w" * 32,
                clock=lambda: 10.0,
            ),
            namespace="witness",
            clock=lambda: 10.0,
        )
        self.signed = AIExecutionEvidenceStore(
            self.backend,
            ArtifactSigner(
                "evidence",
                b"e" * 32,
                clock=lambda: 10.0,
            ),
            namespace="signed",
        )
        self.finalizations = AIExecutionFinalizationStore(
            self.backend,
            namespace="finalizations",
            clock=lambda: 10.0,
        )
        self.finalizer = AIExecutionEvidenceFinalizer(
            journal=self.journal,
            receipt_chain=self.receipts,
            session_evidence=self.session_evidence,
            audit_anchors=self.anchors,
            audit_witnesses=self.witnesses,
            execution_evidence=self.signed,
            finalizations=self.finalizations,
            recovery_checkpoints=self.recovery,
        )

    def reconciler(
        self,
        *,
        recovery=True,
        witness=True,
        signed=True,
    ) -> AIExecutionFinalizationReconciler:
        return AIExecutionFinalizationReconciler(
            finalizations=self.finalizations,
            session_evidence=self.session_evidence,
            audit_anchors=self.anchors,
            recovery_checkpoints=(
                self.recovery if recovery else None
            ),
            audit_witnesses=(
                self.witnesses if witness else None
            ),
            execution_evidence=(
                self.signed if signed else None
            ),
        )

    def finalize(
        self,
        *,
        suffix="",
        seal_id="seal",
    ):
        session, proposal = terminal_session(suffix)
        self.journal.append(
            f"done{suffix}",
            session_id=session.session_id,
            intent_id=session.intent.intent_id,
            proposal_id=proposal.proposal_id,
        )
        execution = execution_bundle(
            session,
            proposal,
            self.receipts,
            suffix=suffix,
        )
        attempt = successful_attempt(
            execution,
            session,
            seal_id=seal_id,
        )
        finalized = self.finalizer.finalize(
            session,
            execution,
            policy_fingerprint=fp("p"),
            tool_catalog_digest=fp("t"),
            effect_digest=fp("e"),
            release_evidence_digest=fp("l"),
            execution_seal_id=seal_id,
            runtime_trust_digest=fp("u"),
            authority_health_policy_digest=fp("h"),
            execution_attempt=attempt,
        )
        return (
            session,
            proposal,
            execution,
            attempt,
            finalized,
        )


def reserve_only(env: Env, *, suffix="", seal_id="seal"):
    session, proposal = terminal_session(suffix)
    env.journal.append(
        f"done{suffix}",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = execution_bundle(
        session,
        proposal,
        env.receipts,
        suffix=suffix,
    )
    attempt = successful_attempt(
        execution,
        session,
        seal_id=seal_id,
    )
    stored = env.finalizations.reserve(
        session_id=session.session_id,
        provenance_digest=execution.provenance.digest,
        execution_attempt_id=attempt.attempt_id,
        execution_attempt_authority_digest=(
            attempt.authority_digest
        ),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
        require_recovery_checkpoint=True,
        require_witness=True,
        require_signed_evidence=True,
    )
    return session, proposal, execution, attempt, stored.finalization


def build_recovery(
    env: Env,
    session,
    execution,
    attempt,
) -> tuple[SessionExecutionEvidence, AIRecoveryCheckpoint]:
    evidence = SessionExecutionEvidence.from_report(
        session.session_id,
        execution.report,
    )
    env.session_evidence.put(evidence)
    session_journal = SessionJournalEvidence.from_journal(
        env.journal,
        session.session_id,
    )
    checkpoint = AISessionCheckpoint.capture(
        session,
        journal_root=env.journal.root_hash(),
        receipt_root=env.receipts.root_hash(),
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
    )
    recovery = AIRecoveryCheckpoint.wrap(
        checkpoint,
        session_evidence_digest=evidence.digest,
        session_journal_digest=session_journal.digest,
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt_id=attempt.attempt_id,
        execution_attempt_authority_digest=(
            attempt.authority_digest
        ),
    )
    return evidence, recovery


def append_anchor(
    env: Env,
    finalization,
    recovery,
    execution,
    evidence,
):
    return env.anchors.append_once(
        finalization_id=finalization.finalization_id,
        session_id=finalization.session_id,
        checkpoint_digest=recovery.digest,
        provenance_digest=execution.provenance.digest,
        journal_root=recovery.session.journal_root,
        receipt_root=recovery.session.receipt_root,
        session_evidence_digest=evidence.digest,
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt_id=(
            finalization.execution_attempt_id
        ),
        execution_attempt_authority_digest=(
            finalization.execution_attempt_authority_digest
        ),
    )


def append_signed(
    env: Env,
    finalization,
    recovery,
    execution,
    evidence,
    anchor,
    witness,
):
    session, _ = terminal_session()
    # Only immutable identity fields are consumed from this temporary object.
    builder = AIExecutionEvidenceBuilder(
        clock=lambda: 10.0
    )
    bundle = builder.build(
        session_id=finalization.session_id,
        intent_fingerprint=execution.provenance.intent_fingerprint,
        proposal_fingerprint=(
            execution.provenance.proposal_fingerprint
        ),
        provenance_digest=execution.provenance.digest,
        checkpoint_digest=recovery.digest,
        session_evidence_digest=evidence.digest,
        session_journal_digest=recovery.session_journal_digest,
        audit_anchor_digest=anchor.anchor.digest,
        audit_chain_node_hash=anchor.chain_node_hash,
        release_evidence_digest=fp("l"),
        execution_seal_id=(
            finalization.execution_attempt_id
        ),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt_id=(
            finalization.execution_attempt_id
        ),
        execution_attempt_authority_digest=(
            finalization.execution_attempt_authority_digest
        ),
        audit_witness_digest=witness.witness.digest,
        audit_witness_sequence=witness.witness.sequence,
        execution_attempt_state="succeeded",
    )
    return env.signed.append_once(bundle)


def test_complete_finalization_inspects_cleanly():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    report = env.reconciler().inspect(
        finalized.finalization.finalization_id
    )
    assert report.ok
    assert not report.safe_to_resume
    assert report.action is FinalizationReconcileAction.COMPLETE
    assert report.reasons == ()
    assert report.session_evidence.verified
    assert report.recovery_checkpoint.verified
    assert report.audit_anchor.verified
    assert report.audit_witness.verified
    assert report.execution_evidence.verified


def test_complete_reconcile_is_idempotent():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    finalization_id = finalized.finalization.finalization_id
    before = env.finalizations.current(
        finalization_id
    )
    report = env.reconciler().reconcile(
        finalization_id
    )
    after = env.finalizations.current(
        finalization_id
    )
    assert report.ok
    assert after == before


def test_started_without_evidence_is_resumable():
    env = Env()
    _, _, _, _, item = reserve_only(env)
    report = env.reconciler().inspect(
        item.finalization_id
    )
    assert report.action is (
        FinalizationReconcileAction.RESUME_FINALIZATION
    )
    assert report.safe_to_resume
    assert not report.session_evidence.present


def test_reconcile_fast_forwards_existing_session_evidence():
    env = Env()
    session, _, execution, _, item = reserve_only(env)
    evidence = SessionExecutionEvidence.from_report(
        session.session_id,
        execution.report,
    )
    env.session_evidence.put(evidence)

    report = env.reconciler().reconcile(
        item.finalization_id
    )
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    assert current.phase is FinalizationPhase.SESSION_EVIDENCE
    assert current.session_evidence_digest == evidence.digest
    assert report.safe_to_resume


def test_reconcile_fast_forwards_matching_recovery_checkpoint():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(
        item.finalization_id,
        recovery,
    )

    report = env.reconciler().reconcile(
        item.finalization_id
    )
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    assert current.phase is FinalizationPhase.CHECKPOINTED
    assert current.session_evidence_digest == evidence.digest
    assert current.recovery_checkpoint_digest == recovery.digest
    assert report.safe_to_resume


def test_recovery_checkpoint_authority_substitution_is_manual_review():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    foreign = replace(
        recovery,
        runtime_trust_digest=fp("x"),
    )
    env.recovery.put(
        item.finalization_id,
        foreign,
    )
    report = env.reconciler().inspect(
        item.finalization_id
    )
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "authority mismatch" in report.recovery_checkpoint.reason
    assert evidence.digest


def test_recovery_checkpoint_missing_on_configured_store_is_resumable():
    env = Env()
    session, _, execution, _, item = reserve_only(env)
    evidence = SessionExecutionEvidence.from_report(
        session.session_id,
        execution.report,
    )
    env.session_evidence.put(evidence)
    item = env.finalizations.advance(
        item,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=evidence.digest,
    ).finalization
    report = env.reconciler().inspect(
        item.finalization_id
    )
    assert report.safe_to_resume
    assert not report.recovery_checkpoint.present


def test_required_recovery_store_unavailable_is_manual_review():
    env = Env()
    _, _, _, _, item = reserve_only(env)
    report = env.reconciler(
        recovery=False,
    ).inspect(item.finalization_id)
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "unavailable" in report.recovery_checkpoint.reason


def test_reconcile_fast_forwards_existing_anchor_and_historical_root():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(
        item.finalization_id,
        recovery,
    )
    anchor = append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )

    report = env.reconciler().reconcile(
        item.finalization_id
    )
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    assert current.phase is FinalizationPhase.ANCHORED
    assert current.audit_anchor_digest == anchor.anchor.digest
    assert current.audit_chain_node_hash == anchor.chain_node_hash
    assert current.audit_root == anchor.chain_node_hash
    assert report.safe_to_resume


def test_anchor_fast_forward_works_after_newer_global_anchor():
    env = Env()
    session, _, execution, attempt, item = reserve_only(
        env,
        suffix="-old",
        seal_id="old-seal",
    )
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(
        item.finalization_id,
        recovery,
    )
    old_anchor = append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )

    # Advance the global chain with a different finalization before reconciling
    # the older state record.
    env.finalize(
        suffix="-new",
        seal_id="new-seal",
    )
    assert env.anchors.root_hash() != old_anchor.chain_node_hash

    env.reconciler().reconcile(
        item.finalization_id
    )
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    assert current.audit_root == old_anchor.chain_node_hash
    assert current.audit_chain_node_hash == old_anchor.chain_node_hash


def test_anchor_provenance_substitution_is_manual_review():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    env.anchors.append_once(
        finalization_id=item.finalization_id,
        session_id=item.session_id,
        checkpoint_digest=recovery.digest,
        provenance_digest=fp("x"),
        journal_root=recovery.session.journal_root,
        receipt_root=recovery.session.receipt_root,
        session_evidence_digest=evidence.digest,
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt_id=item.execution_attempt_id,
        execution_attempt_authority_digest=(
            item.execution_attempt_authority_digest
        ),
    )
    report = env.reconciler().inspect(
        item.finalization_id
    )
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "provenance" in report.audit_anchor.reason


def test_required_witness_missing_is_resumable():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )
    env.reconciler().reconcile(item.finalization_id)
    report = env.reconciler().inspect(item.finalization_id)
    assert report.safe_to_resume
    assert report.audit_witness.expected
    assert not report.audit_witness.present


def test_required_witness_store_unavailable_is_manual_review():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    report = env.reconciler(
        witness=False,
    ).inspect(finalized.finalization.finalization_id)
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "unavailable" in report.audit_witness.reason


def test_reconcile_fast_forwards_matching_witness():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    anchor = append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )
    # First reconcile establishes the historical audit root.
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    witness = env.witnesses.publish_once(
        current.audit_root,
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )

    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    assert current.phase is FinalizationPhase.WITNESSED
    assert current.audit_witness_digest == witness.witness.digest
    assert current.audit_witness_sequence == witness.witness.sequence
    assert current.audit_anchor_digest == anchor.anchor.digest


def test_witness_trust_substitution_is_not_considered_present():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(
        item.finalization_id
    ).finalization
    env.witnesses.publish_once(
        current.audit_root,
        runtime_trust_digest=fp("x"),
        release_evidence_digest=fp("l"),
    )
    report = env.reconciler().inspect(item.finalization_id)
    assert report.safe_to_resume
    assert not report.audit_witness.present


def test_required_signed_evidence_missing_is_resumable():
    env = Env()
    # Create through witness, but do not append top-level signed evidence.
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    append_anchor(env, item, recovery, execution, evidence)
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    env.witnesses.publish_once(
        current.audit_root,
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    env.reconciler().reconcile(item.finalization_id)
    report = env.reconciler().inspect(item.finalization_id)
    assert report.safe_to_resume
    assert report.execution_evidence.expected
    assert not report.execution_evidence.present


def test_required_signed_store_unavailable_is_manual_review():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    report = env.reconciler(
        signed=False,
    ).inspect(finalized.finalization.finalization_id)
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "unavailable" in report.execution_evidence.reason


def test_reconcile_fast_forwards_matching_signed_evidence_to_complete():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    anchor = append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    witness = env.witnesses.publish_once(
        current.audit_root,
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    signed = append_signed(
        env,
        current,
        recovery,
        execution,
        evidence,
        anchor,
        witness,
    )

    report = env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    assert report.ok
    assert current.phase is FinalizationPhase.COMPLETE
    assert current.execution_evidence_digest == signed.evidence.digest
    assert (
        current.execution_evidence_chain_node_hash
        == signed.chain_node_hash
    )


def test_signed_evidence_provenance_substitution_is_manual_review():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    anchor = append_anchor(env, item, recovery, execution, evidence)
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    witness = env.witnesses.publish_once(
        current.audit_root,
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    builder = AIExecutionEvidenceBuilder(clock=lambda: 10.0)
    foreign = builder.build(
        session_id=item.session_id,
        intent_fingerprint=execution.provenance.intent_fingerprint,
        proposal_fingerprint=execution.provenance.proposal_fingerprint,
        provenance_digest=fp("x"),
        checkpoint_digest=recovery.digest,
        session_evidence_digest=evidence.digest,
        session_journal_digest=recovery.session_journal_digest,
        audit_anchor_digest=anchor.anchor.digest,
        audit_chain_node_hash=anchor.chain_node_hash,
        release_evidence_digest=fp("l"),
        execution_seal_id=item.execution_attempt_id,
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt_id=item.execution_attempt_id,
        execution_attempt_authority_digest=(
            item.execution_attempt_authority_digest
        ),
        audit_witness_digest=witness.witness.digest,
        audit_witness_sequence=witness.witness.sequence,
        execution_attempt_state="succeeded",
    )
    env.signed.append_once(foreign)

    report = env.reconciler().inspect(item.finalization_id)
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "provenance" in report.execution_evidence.reason


def test_session_evidence_digest_mismatch_is_manual_review():
    env = Env()
    session, _, execution, _, item = reserve_only(env)
    evidence = SessionExecutionEvidence.from_report(
        session.session_id,
        execution.report,
    )
    env.session_evidence.put(evidence)
    item = env.finalizations.advance(
        item,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("x"),
    ).finalization
    report = env.reconciler().inspect(item.finalization_id)
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "digest mismatch" in report.session_evidence.reason


def test_missing_expected_session_evidence_is_resumable():
    env = Env()
    _, _, _, _, item = reserve_only(env)
    # Force state to claim session evidence without storing it.
    item = env.finalizations.advance(
        item,
        FinalizationPhase.SESSION_EVIDENCE,
        session_evidence_digest=fp("s"),
    ).finalization
    report = env.reconciler().inspect(item.finalization_id)
    assert report.safe_to_resume
    assert "missing" in report.session_evidence.reason


def test_anchor_chain_corruption_is_manual_review():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    node = env.anchors._chain.snapshot()[0]
    record = env.backend.get(
        env.anchors._chain.namespace,
        f"node:{node.node_hash}",
    )
    env.backend.compare_and_swap(
        env.anchors._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload={"corrupt": True},
        ),
    )
    report = env.reconciler().inspect(
        finalized.finalization.finalization_id
    )
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "integrity" in report.audit_anchor.reason


def test_signed_chain_corruption_is_manual_review():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    node = env.signed._chain.snapshot()[0]
    record = env.backend.get(
        env.signed._chain.namespace,
        f"node:{node.node_hash}",
    )
    env.backend.compare_and_swap(
        env.signed._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload={"corrupt": True},
        ),
    )
    report = env.reconciler().inspect(
        finalized.finalization.finalization_id
    )
    assert report.action is FinalizationReconcileAction.MANUAL_REVIEW
    assert "integrity" in report.execution_evidence.reason


def test_reconciler_missing_finalization_raises():
    env = Env()
    with pytest.raises(
        ExecutionFinalizationConflict,
        match="missing",
    ):
        env.reconciler().inspect("missing")
    with pytest.raises(
        ExecutionFinalizationConflict,
        match="missing",
    ):
        env.reconciler().reconcile("missing")


def test_report_to_dict_is_json_shaped():
    env = Env()
    _, _, _, _, finalized = env.finalize()
    report = env.reconciler().inspect(
        finalized.finalization.finalization_id
    )
    data = report.to_dict()
    assert data["action"] == "complete"
    assert data["ok"] is True
    assert data["safe_to_resume"] is False
    assert data["audit_anchor"]["verified"] is True
    assert data["audit_witness"]["verified"] is True
    assert data["execution_evidence"]["verified"] is True


def test_optional_capability_absence_does_not_force_manual_review():
    backend = InMemoryFencedStore()
    journal = AIDecisionJournal(clock=lambda: 10.0)
    receipts = ReceiptChain()
    session_evidence = SessionEvidenceStore(
        backend,
        namespace="session",
    )
    anchors = AIAuditAnchorStore(
        backend,
        ArtifactSigner("audit", b"a" * 32),
        namespace="anchors",
    )
    finalizations = AIExecutionFinalizationStore(
        backend,
        namespace="finalization",
    )
    session, proposal = terminal_session()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = execution_bundle(
        session,
        proposal,
        receipts,
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=session_evidence,
        audit_anchors=anchors,
        finalizations=finalizations,
    )
    result = finalizer.finalize(
        session,
        execution,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
    )
    reconciler = AIExecutionFinalizationReconciler(
        finalizations=finalizations,
        session_evidence=session_evidence,
        audit_anchors=anchors,
    )
    report = reconciler.inspect(
        result.finalization.finalization_id
    )
    assert report.ok
    assert not result.finalization.require_recovery_checkpoint
    assert not result.finalization.require_witness
    assert not result.finalization.require_signed_evidence


def test_reconcile_does_not_complete_when_required_layer_missing():
    env = Env()
    session, _, execution, attempt, item = reserve_only(env)
    evidence, recovery = build_recovery(
        env,
        session,
        execution,
        attempt,
    )
    env.recovery.put(item.finalization_id, recovery)
    append_anchor(
        env,
        item,
        recovery,
        execution,
        evidence,
    )
    report = env.reconciler().reconcile(item.finalization_id)
    current = env.finalizations.current(item.finalization_id).finalization
    assert current.phase is FinalizationPhase.ANCHORED
    assert report.safe_to_resume
    assert not report.ok
    assert not report.audit_witness.present
    assert not report.execution_evidence.present
