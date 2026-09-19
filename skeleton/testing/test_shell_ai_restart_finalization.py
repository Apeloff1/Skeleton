"""Restart-idempotent AI execution evidence finalization integration tests."""

from __future__ import annotations

import hashlib
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
from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceStore
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalizationStore,
    FinalizationPhase,
)
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.provenance import AIDecisionProvenance
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.session_evidence import SessionEvidenceStore
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.plan_executor import (
    PlanExecutionReport,
    StepExecution,
    StepState,
)
from skeleton.shells.receipts import ReceiptChain


def fp(char: str) -> str:\n    return hashlib.sha256(char.encode()).hexdigest()


def completed_session(
    suffix: str = "",
) -> tuple[AIShellSession, AIPlanProposal]:
    intent = AIIntent(
        f"intent{suffix}",
        f"complete test plan {suffix}",
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


def bundle(
    session: AIShellSession,
    proposal: AIPlanProposal,
    receipts: ReceiptChain,
    *,
    suffix: str = "",
) -> SimpleNamespace:
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
    session: AIShellSession,
    *,
    seal_id: str,
) -> AIExecutionAttempt:
    return AIExecutionAttempt(
        1,
        seal_id,
        session.session_id,
        "alice",
        "worker-1",
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


class FailAnchorVerifyOnce(AIAuditAnchorStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_once = True

    def verify(self) -> bool:
        if self.fail_once and self._chain.length() > 0:
            self.fail_once = False
            return False
        return super().verify()


class FailWitnessRequireOnce(AIAuditWitnessStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_once = True

    def require_witness(self, item):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("synthetic witness post-publish crash")
        return super().require_witness(item)


class FailExecutionVerifyOnce(AIExecutionEvidenceStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_once = True

    def verify(self) -> bool:
        if self.fail_once and self._chain.length() > 0:
            self.fail_once = False
            return False
        return super().verify()


def environment(
    *,
    anchor_class=AIAuditAnchorStore,
    witness_class=AIAuditWitnessStore,
    evidence_class=AIExecutionEvidenceStore,
):
    backend = InMemoryFencedStore()
    journal = AIDecisionJournal(clock=lambda: 10.0)
    receipts = ReceiptChain()
    session_evidence = SessionEvidenceStore(
        backend,
        namespace="session-evidence",
    )
    anchors = anchor_class(
        backend,
        ArtifactSigner(
            "audit",
            b"a" * 32,
            clock=lambda: 10.0,
        ),
        namespace="audit",
        clock=lambda: 10.0,
    )
    witnesses = witness_class(
        backend,
        ArtifactSigner(
            "witness",
            b"w" * 32,
            clock=lambda: 10.0,
        ),
        namespace="witness",
        clock=lambda: 10.0,
    )
    execution_evidence = evidence_class(
        backend,
        ArtifactSigner(
            "execution",
            b"e" * 32,
            clock=lambda: 10.0,
        ),
        namespace="execution-evidence",
    )
    finalizations = AIExecutionFinalizationStore(
        backend,
        namespace="finalization",
        clock=lambda: 10.0,
    )
    finalizer = AIExecutionEvidenceFinalizer(
        journal=journal,
        receipt_chain=receipts,
        session_evidence=session_evidence,
        audit_anchors=anchors,
        audit_witnesses=witnesses,
        execution_evidence=execution_evidence,
        finalizations=finalizations,
    )
    return (
        backend,
        journal,
        receipts,
        session_evidence,
        anchors,
        witnesses,
        execution_evidence,
        finalizations,
        finalizer,
    )


def finalize_once(
    finalizer,
    journal,
    receipts,
    *,
    suffix="",
    seal_id="seal-1",
):
    session, proposal = completed_session(suffix)
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = bundle(
        session,
        proposal,
        receipts,
        suffix=suffix,
    )
    attempt = successful_attempt(
        execution,
        session,
        seal_id=seal_id,
    )
    result = finalizer.finalize(
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
    return session, proposal, execution, attempt, result


def test_full_finalization_is_complete_and_cross_bound():
    (
        _,
        journal,
        receipts,
        _,
        anchors,
        witnesses,
        evidence,
        finalizations,
        finalizer,
    ) = environment()
    _, _, execution, attempt, result = finalize_once(
        finalizer,
        journal,
        receipts,
    )
    assert result.finalization is not None
    assert result.finalization.phase is FinalizationPhase.COMPLETE
    assert result.finalization.execution_attempt_id == attempt.attempt_id
    assert (
        result.finalization.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert (
        result.recovery_checkpoint.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert (
        result.audit_anchor.anchor.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert result.execution_evidence is not None
    assert (
        result.execution_evidence.evidence.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert result.execution_evidence.evidence.execution_attempt_state == "succeeded"
    assert result.finalization.provenance_digest == execution.provenance.digest
    assert anchors.verify()
    assert witnesses.verify().ok
    assert evidence.verify()
    assert finalizations.require_complete(
        result.finalization.finalization_id
    ) == result.finalization


def test_full_finalization_retry_is_chain_idempotent():
    (
        _,
        journal,
        receipts,
        _,
        anchors,
        witnesses,
        evidence,
        finalizations,
        finalizer,
    ) = environment()
    session, proposal = completed_session()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = bundle(session, proposal, receipts)
    attempt = successful_attempt(
        execution,
        session,
        seal_id="seal-1",
    )
    kwargs = dict(
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-1",
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt=attempt,
    )
    first = finalizer.finalize(
        session,
        execution,
        **kwargs,
    )
    first_revision = finalizations.current(
        first.finalization.finalization_id
    ).revision
    second = finalizer.finalize(
        session,
        execution,
        **kwargs,
    )
    second_revision = finalizations.current(
        second.finalization.finalization_id
    ).revision

    assert len(anchors.snapshot()) == 1
    assert witnesses.current_head()[1].sequence == 1
    assert len(evidence.snapshot()) == 1
    assert second_revision == first_revision
    assert second.audit_anchor.chain_node_hash == first.audit_anchor.chain_node_hash
    assert second.audit_witness.witness.digest == first.audit_witness.witness.digest
    assert (
        second.execution_evidence.chain_node_hash
        == first.execution_evidence.chain_node_hash
    )
    assert second.finalization == first.finalization


def test_retry_after_later_session_reuses_historical_witness():
    (
        _,
        journal,
        receipts,
        _,
        anchors,
        witnesses,
        evidence,
        finalizations,
        finalizer,
    ) = environment()

    session1, proposal1 = completed_session("-one")
    journal.append(
        "done-one",
        session_id=session1.session_id,
        intent_id=session1.intent.intent_id,
        proposal_id=proposal1.proposal_id,
    )
    execution1 = bundle(
        session1,
        proposal1,
        receipts,
        suffix="-one",
    )
    attempt1 = successful_attempt(
        execution1,
        session1,
        seal_id="seal-one",
    )
    args1 = dict(
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-one",
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt=attempt1,
    )
    first = finalizer.finalize(
        session1,
        execution1,
        **args1,
    )
    first_witness = first.audit_witness.witness.digest
    first_root = first.finalization.audit_root

    session2, proposal2 = completed_session("-two")
    journal.append(
        "done-two",
        session_id=session2.session_id,
        intent_id=session2.intent.intent_id,
        proposal_id=proposal2.proposal_id,
    )
    execution2 = bundle(
        session2,
        proposal2,
        receipts,
        suffix="-two",
    )
    attempt2 = successful_attempt(
        execution2,
        session2,
        seal_id="seal-two",
    )
    second = finalizer.finalize(
        session2,
        execution2,
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-two",
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt=attempt2,
    )
    assert second.finalization.audit_root != first_root
    assert witnesses.current_head()[1].sequence == 2

    retried = finalizer.finalize(
        session1,
        execution1,
        **args1,
    )
    assert retried.finalization.audit_root == first_root
    assert retried.audit_witness.witness.digest == first_witness
    assert retried.audit_witness.witness.sequence == 1
    assert witnesses.current_head()[1].sequence == 2
    assert len(anchors.snapshot()) == 2
    assert len(evidence.snapshot()) == 2
    assert finalizations.require_complete(
        first.finalization.finalization_id
    ).audit_root == first_root


def test_crash_after_anchor_append_resumes_without_duplicate_anchor():
    (
        _,
        journal,
        receipts,
        _,
        anchors,
        witnesses,
        evidence,
        finalizations,
        finalizer,
    ) = environment(anchor_class=FailAnchorVerifyOnce)
    session, proposal = completed_session()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = bundle(session, proposal, receipts)
    attempt = successful_attempt(
        execution,
        session,
        seal_id="seal-anchor",
    )
    kwargs = dict(
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-anchor",
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt=attempt,
    )

    with pytest.raises(RuntimeError, match="anchor chain"):
        finalizer.finalize(
            session,
            execution,
            **kwargs,
        )
    assert len(anchors.snapshot()) == 1
    finalization_id = next(
        item.anchor.finalization_id
        for item in anchors.snapshot()
    )
    partial = finalizations.current(finalization_id).finalization
    assert partial.phase is FinalizationPhase.CHECKPOINTED

    result = finalizer.finalize(
        session,
        execution,
        **kwargs,
    )
    assert result.finalization.phase is FinalizationPhase.COMPLETE
    assert len(anchors.snapshot()) == 1
    assert witnesses.current_head()[1].sequence == 1
    assert len(evidence.snapshot()) == 1


def test_crash_after_witness_publish_resumes_without_duplicate_witness():
    (
        _,
        journal,
        receipts,
        _,
        anchors,
        witnesses,
        evidence,
        finalizations,
        finalizer,
    ) = environment(witness_class=FailWitnessRequireOnce)
    session, proposal = completed_session()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = bundle(session, proposal, receipts)
    attempt = successful_attempt(
        execution,
        session,
        seal_id="seal-witness",
    )
    kwargs = dict(
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-witness",
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt=attempt,
    )

    with pytest.raises(RuntimeError, match="synthetic witness"):
        finalizer.finalize(
            session,
            execution,
            **kwargs,
        )
    assert len(anchors.snapshot()) == 1
    assert witnesses.current_head()[1].sequence == 1
    finalization_id = anchors.snapshot()[0].anchor.finalization_id
    partial = finalizations.current(finalization_id).finalization
    assert partial.phase is FinalizationPhase.ANCHORED

    result = finalizer.finalize(
        session,
        execution,
        **kwargs,
    )
    assert result.finalization.phase is FinalizationPhase.COMPLETE
    assert witnesses.current_head()[1].sequence == 1
    assert len(anchors.snapshot()) == 1
    assert len(evidence.snapshot()) == 1


def test_crash_after_execution_evidence_append_resumes_without_duplicate_bundle():
    (
        _,
        journal,
        receipts,
        _,
        anchors,
        witnesses,
        evidence,
        finalizations,
        finalizer,
    ) = environment(evidence_class=FailExecutionVerifyOnce)
    session, proposal = completed_session()
    journal.append(
        "done",
        session_id=session.session_id,
        intent_id=session.intent.intent_id,
        proposal_id=proposal.proposal_id,
    )
    execution = bundle(session, proposal, receipts)
    attempt = successful_attempt(
        execution,
        session,
        seal_id="seal-evidence",
    )
    kwargs = dict(
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        release_evidence_digest=fp("l"),
        execution_seal_id="seal-evidence",
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
        execution_attempt=attempt,
    )

    with pytest.raises(RuntimeError, match="execution evidence chain"):
        finalizer.finalize(
            session,
            execution,
            **kwargs,
        )
    assert len(evidence.snapshot()) == 1
    finalization_id = anchors.snapshot()[0].anchor.finalization_id
    partial = finalizations.current(finalization_id).finalization
    assert partial.phase is FinalizationPhase.WITNESSED

    result = finalizer.finalize(
        session,
        execution,
        **kwargs,
    )
    assert result.finalization.phase is FinalizationPhase.COMPLETE
    assert len(evidence.snapshot()) == 1
    assert witnesses.current_head()[1].sequence == 1
    assert len(anchors.snapshot()) == 1


def test_anchor_append_once_rejects_finalization_id_substitution():
    (
        _,
        _,
        _,
        _,
        anchors,
        _,
        _,
        _,
        _,
    ) = environment()
    first = anchors.append_once(
        finalization_id="finalization",
        session_id="session",
        checkpoint_digest=fp("c"),
        provenance_digest=fp("p"),
        journal_root=fp("j"),
        receipt_root=fp("r"),
        session_evidence_digest=fp("s"),
    )
    with pytest.raises(RuntimeError, match="different audit anchor"):
        anchors.append_once(
            finalization_id="finalization",
            session_id="other",
            checkpoint_digest=fp("c"),
            provenance_digest=fp("p"),
            journal_root=fp("j"),
            receipt_root=fp("r"),
            session_evidence_digest=fp("s"),
        )
    assert len(anchors.snapshot()) == 1
    assert anchors.snapshot()[0].anchor.digest == first.anchor.digest


def test_execution_evidence_append_once_rejects_attempt_substitution():
    (
        _,
        _,
        _,
        _,
        _,
        _,
        evidence,
        _,
        _,
    ) = environment()
    from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceBuilder

    builder = AIExecutionEvidenceBuilder(clock=lambda: 1.0)
    first = builder.build(
        session_id="s",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        provenance_digest=fp("v"),
        checkpoint_digest=fp("c"),
        session_evidence_digest=fp("s"),
        session_journal_digest=fp("j"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("x"),
        execution_attempt_state="succeeded",
    )
    evidence.append_once(first)
    second = builder.build(
        session_id="s",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        provenance_digest=fp("z"),
        checkpoint_digest=fp("c"),
        session_evidence_digest=fp("s"),
        session_journal_digest=fp("j"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("x"),
        execution_attempt_state="succeeded",
    )
    with pytest.raises(RuntimeError, match="different final evidence"):
        evidence.append_once(second)
    assert len(evidence.snapshot()) == 1


def test_witness_publish_once_returns_existing_exact_witness():
    (
        _,
        _,
        _,
        _,
        _,
        witnesses,
        _,
        _,
        _,
    ) = environment()
    first = witnesses.publish_once(
        fp("a"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    second = witnesses.publish_once(
        fp("a"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    assert second == first
    assert witnesses.current_head()[1].sequence == 1


def test_witness_find_can_resolve_historical_canonical_item():
    (
        _,
        _,
        _,
        _,
        _,
        witnesses,
        _,
        _,
        _,
    ) = environment()
    first = witnesses.publish_once(
        fp("a"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    witnesses.publish_once(
        fp("b"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    found = witnesses.find(
        fp("a"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    assert found == first
    assert witnesses.require_witness(found) == first
    assert witnesses.current_head()[1].sequence == 2


def test_witness_find_distinguishes_runtime_trust():
    (
        _,
        _,
        _,
        _,
        _,
        witnesses,
        _,
        _,
        _,
    ) = environment()
    witnesses.publish_once(
        fp("a"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    assert (
        witnesses.find(
            fp("a"),
            runtime_trust_digest=fp("x"),
            release_evidence_digest=fp("l"),
        )
        is None
    )


def test_witness_find_distinguishes_release_evidence():
    (
        _,
        _,
        _,
        _,
        _,
        witnesses,
        _,
        _,
        _,
    ) = environment()
    witnesses.publish_once(
        fp("a"),
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
    )
    assert (
        witnesses.find(
            fp("a"),
            runtime_trust_digest=fp("u"),
            release_evidence_digest=fp("x"),
        )
        is None
    )


def test_finalization_result_serializes_progress_record():
    (
        _,
        journal,
        receipts,
        _,
        _,
        _,
        _,
        _,
        finalizer,
    ) = environment()
    _, _, _, _, result = finalize_once(
        finalizer,
        journal,
        receipts,
    )
    data = result.to_dict()
    assert data["finalization"]["phase"] == "complete"
    assert data["finalization"]["recovery"] == "complete"
    assert len(data["finalization"]["binding_digest"]) == 64
