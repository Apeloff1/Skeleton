"""Finalize completed AI execution into restart and audit evidence."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore, SignedAIAuditAnchor
from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.orchestrator import AIExecutionBundle
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.session import AIShellSession
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
    SessionExecutionEvidence,
)
from skeleton.shells.ai.session_journal import SessionJournalEvidence


@dataclass(frozen=True)
class FinalizedAIExecutionEvidence:
    checkpoint: AISessionCheckpoint
    recovery_checkpoint: AIRecoveryCheckpoint
    session_evidence: SessionExecutionEvidence
    session_journal: SessionJournalEvidence
    audit_anchor: SignedAIAuditAnchor

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "checkpoint_digest": self.checkpoint.digest,
            "recovery_checkpoint": self.recovery_checkpoint.to_dict(),
            "recovery_checkpoint_digest": self.recovery_checkpoint.digest,
            "session_evidence": self.session_evidence.to_dict(),
            "session_evidence_digest": self.session_evidence.digest,
            "session_journal": self.session_journal.to_dict(),
            "session_journal_digest": self.session_journal.digest,
            "audit_anchor": self.audit_anchor.to_dict(),
        }


class AIExecutionEvidenceFinalizer:
    """Commit the evidence required to recover or audit one finished session.

    This class does not execute commands and does not call a model. It consumes
    evidence already produced by the reviewed execution path.
    """

    def __init__(
        self,
        *,
        journal,
        receipt_chain,
        session_evidence: SessionEvidenceStore,
        audit_anchors: AIAuditAnchorStore,
    ) -> None:
        self.journal = journal
        self.receipt_chain = receipt_chain
        self.session_evidence = session_evidence
        self.audit_anchors = audit_anchors

    def finalize(
        self,
        session: AIShellSession,
        execution: AIExecutionBundle,
        *,
        policy_fingerprint: str,
        tool_catalog_digest: str,
        effect_digest: str,
        release_evidence_digest: str = "",
        sandbox_binding_digest: str = "",
    ) -> FinalizedAIExecutionEvidence:
        if session.phase.value not in {"complete", "failed"}:
            raise RuntimeError("AI execution evidence may only finalize a completed attempt")
        if execution.review.planning.response.proposal is not session.proposal:
            # Identity is deliberately strict here. A finalizer should receive
            # the exact proposal object held by the session that executed it.
            raise RuntimeError("execution bundle does not belong to session proposal")
        if execution.provenance.intent_fingerprint != session.intent.fingerprint:
            raise RuntimeError("execution provenance intent does not match session")
        if execution.provenance.proposal_fingerprint != session.proposal.fingerprint:
            raise RuntimeError("execution provenance proposal does not match session")
        if execution.provenance.policy_fingerprint != policy_fingerprint:
            raise RuntimeError("execution provenance policy differs from finalizer policy")
        if execution.provenance.tool_catalog_digest != tool_catalog_digest:
            raise RuntimeError("execution provenance tool catalog differs from finalizer")
        if execution.provenance.effect_digest != effect_digest:
            raise RuntimeError("execution provenance effect registry differs from finalizer")
        if release_evidence_digest and (
            execution.provenance.release_evidence_digest != release_evidence_digest
        ):
            raise RuntimeError("execution provenance release evidence differs from finalizer")
        if sandbox_binding_digest and (
            execution.provenance.sandbox_binding_digest != sandbox_binding_digest
        ):
            raise RuntimeError("execution provenance sandbox binding differs from finalizer")
        if not self.journal.verify():
            raise RuntimeError("AI decision journal failed integrity verification")
        if not self.receipt_chain.verify():
            raise RuntimeError("shell receipt chain failed integrity verification")

        evidence = SessionExecutionEvidence.from_report(
            session.session_id,
            execution.report,
        )
        stored = self.session_evidence.put(evidence)
        if stored.evidence.digest != evidence.digest:
            raise RuntimeError("stored session execution evidence differs from final evidence")

        session_journal = SessionJournalEvidence.from_journal(
            self.journal,
            session.session_id,
        )
        checkpoint = AISessionCheckpoint.capture(
            session,
            journal_root=self.journal.root_hash(),
            receipt_root=self.receipt_chain.root_hash(),
            policy_fingerprint=policy_fingerprint,
            tool_catalog_digest=tool_catalog_digest,
            effect_digest=effect_digest,
        )
        recovery = AIRecoveryCheckpoint.wrap(
            checkpoint,
            session_evidence_digest=evidence.digest,
            session_journal_digest=session_journal.digest,
            release_evidence_digest=release_evidence_digest,
            sandbox_binding_digest=sandbox_binding_digest,
        )
        anchor = self.audit_anchors.append(
            session_id=session.session_id,
            checkpoint_digest=recovery.digest,
            provenance_digest=execution.provenance.digest,
            journal_root=checkpoint.journal_root,
            receipt_root=checkpoint.receipt_root,
            session_evidence_digest=evidence.digest,
            release_evidence_digest=release_evidence_digest,
            sandbox_binding_digest=sandbox_binding_digest,
        )
        if not self.audit_anchors.verify():
            raise RuntimeError("AI audit anchor chain failed verification after append")
        return FinalizedAIExecutionEvidence(
            checkpoint,
            recovery,
            evidence,
            session_journal,
            anchor,
        )
