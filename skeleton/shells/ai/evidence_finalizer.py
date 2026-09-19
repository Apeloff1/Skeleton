"""Finalize completed AI execution into restart and audit evidence."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore, SignedAIAuditAnchor
from skeleton.shells.ai.audit_witness import (
    AIAuditWitnessStore,
    SignedAIAuditWitness,
)
from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.durable_root_protection import (
    DurableFinalizationRootProtections,
    DurableRootProtectionStore,
)
from skeleton.shells.ai.durable_session_commit import (
    DurableSessionCommitBuilder,
    DurableSessionCommitPublication,
    DurableSessionCommitStore,
)
from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalCommit,
    DurableSessionJournalStore,
)
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    ExecutionAttemptState,
)
from skeleton.shells.ai.orchestrator import AIExecutionBundle
from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceBuilder, AIExecutionEvidenceStore, SignedAIExecutionEvidence
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    AIExecutionFinalizationStore,
    FinalizationPhase,
)
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.recovery_store import (
    AIRecoveryCheckpointStore,
    RecoveryCheckpointCommit,
)
from skeleton.shells.ai.session import AIShellSession
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
    SessionExecutionEvidence,
)
from skeleton.shells.ai.session_journal import SessionJournalEvidence
from skeleton.shells.ai.session_integrity import (
    SessionEvidenceIntegrityReport,
    SessionEvidenceIntegrityVerifier,
)


@dataclass(frozen=True)
class FinalizedAIExecutionEvidence:
    checkpoint: AISessionCheckpoint
    recovery_checkpoint: AIRecoveryCheckpoint
    session_evidence: SessionExecutionEvidence
    session_journal: SessionJournalEvidence
    audit_anchor: SignedAIAuditAnchor
    audit_witness: SignedAIAuditWitness | None = None
    execution_evidence: SignedAIExecutionEvidence | None = None
    finalization: AIExecutionFinalization | None = None
    recovery_commit: RecoveryCheckpointCommit | None = None
    session_integrity: SessionEvidenceIntegrityReport | None = None
    session_journal_commit: DurableSessionJournalCommit | None = None
    session_commit: DurableSessionCommitPublication | None = None
    root_protections: DurableFinalizationRootProtections | None = None

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
            "audit_witness": (
                None
                if self.audit_witness is None
                else self.audit_witness.to_dict()
            ),
            "execution_evidence": (
                None
                if self.execution_evidence is None
                else self.execution_evidence.to_dict()
            ),
            "finalization": (
                None
                if self.finalization is None
                else self.finalization.to_dict()
            ),
            "recovery_commit": (
                None
                if self.recovery_commit is None
                else self.recovery_commit.to_dict()
            ),
            "session_integrity": (
                None
                if self.session_integrity is None
                else self.session_integrity.to_dict()
            ),
            "session_journal_commit": (
                None
                if self.session_journal_commit is None
                else self.session_journal_commit.to_dict()
            ),
            "session_commit": (
                None
                if self.session_commit is None
                else self.session_commit.to_dict()
            ),
            "root_protections": (
                None
                if self.root_protections is None
                else self.root_protections.to_dict()
            ),
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
        audit_witnesses: AIAuditWitnessStore | None = None,
        execution_evidence: AIExecutionEvidenceStore | None = None,
        execution_evidence_builder: AIExecutionEvidenceBuilder | None = None,
        finalizations: AIExecutionFinalizationStore | None = None,
        recovery_checkpoints: AIRecoveryCheckpointStore | None = None,
        integrity_verifier: SessionEvidenceIntegrityVerifier | None = None,
        session_journals: DurableSessionJournalStore | None = None,
        session_commits: DurableSessionCommitStore | None = None,
        session_commit_builder: DurableSessionCommitBuilder | None = None,
        root_protection_store: DurableRootProtectionStore | None = None,
        journal_chain_id: str = "",
        receipt_chain_id: str = "",
    ) -> None:
        self.journal = journal
        self.receipt_chain = receipt_chain
        self.session_evidence = session_evidence
        self.audit_anchors = audit_anchors
        self.audit_witnesses = audit_witnesses
        self.execution_evidence = execution_evidence
        self.execution_evidence_builder = (
            execution_evidence_builder or AIExecutionEvidenceBuilder()
        )
        self.finalizations = finalizations
        self.recovery_checkpoints = recovery_checkpoints
        self.session_journals = session_journals
        self.session_commits = session_commits
        self.session_commit_builder = (
            session_commit_builder
            or DurableSessionCommitBuilder()
        )
        if root_protection_store is not None and not isinstance(
            root_protection_store,
            DurableRootProtectionStore,
        ):
            raise TypeError(
                "root_protection_store must be DurableRootProtectionStore"
            )
        if root_protection_store is None:
            if journal_chain_id or receipt_chain_id:
                raise ValueError(
                    "root protection chain ids require root_protection_store"
                )
        else:
            if not journal_chain_id or not receipt_chain_id:
                raise ValueError(
                    "root protection store requires journal and receipt chain ids"
                )
            if (
                len(journal_chain_id) > 128
                or len(receipt_chain_id) > 128
            ):
                raise ValueError(
                    "root protection chain id too long"
                )
            if journal_chain_id == receipt_chain_id:
                raise ValueError(
                    "journal and receipt protection chain ids must differ"
                )
        self.root_protection_store = root_protection_store
        self.journal_chain_id = journal_chain_id
        self.receipt_chain_id = receipt_chain_id
        policy = self.session_commit_builder.policy
        if self.session_commits is not None:
            if self.finalizations is None:
                raise ValueError(
                    "durable session commits require finalization store"
                )
            if (
                policy.require_recovery_checkpoint
                and self.recovery_checkpoints is None
            ):
                raise ValueError(
                    "session commit policy requires recovery checkpoint store"
                )
            if (
                policy.require_session_journal_manifest
                and self.session_journals is None
            ):
                raise ValueError(
                    "session commit policy requires durable session-journal store"
                )
            if (
                policy.require_audit_witness
                and self.audit_witnesses is None
            ):
                raise ValueError(
                    "session commit policy requires audit witness store"
                )
            if (
                policy.require_signed_execution_evidence
                and self.execution_evidence is None
            ):
                raise ValueError(
                    "session commit policy requires signed execution evidence store"
                )
            if (
                policy.require_root_protection
                and self.root_protection_store is None
            ):
                raise ValueError(
                    "session commit policy requires root protection store"
                )
        self.integrity_verifier = (
            integrity_verifier
            or SessionEvidenceIntegrityVerifier(
                journal,
                receipt_chain,
            )
        )

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
        model_attestation_digest: str = "",
        execution_seal_id: str = "",
        quorum_approval_digest: str = "",
        runtime_trust_digest: str = "",
        authority_health_policy_digest: str = "",
        execution_attempt_authority_digest: str = "",
        execution_attempt: AIExecutionAttempt | None = None,
    ) -> FinalizedAIExecutionEvidence:
        if session.phase.value not in {"complete", "failed"}:
            raise RuntimeError("AI execution evidence may only finalize a completed attempt")
        reviewed_proposal = execution.review.planning.response.proposal
        if session.proposal is None:
            raise RuntimeError("AI session has no proposal to finalize")
        if (
            reviewed_proposal.proposal_id != session.proposal.proposal_id
            or reviewed_proposal.fingerprint != session.proposal.fingerprint
        ):
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
        if runtime_trust_digest and (
            execution.provenance.runtime_trust_digest != runtime_trust_digest
        ):
            raise RuntimeError(
                "execution provenance runtime trust differs from finalizer"
            )
        if authority_health_policy_digest and (
            execution.provenance.authority_health_policy_digest
            != authority_health_policy_digest
        ):
            raise RuntimeError(
                "execution provenance authority health policy differs from finalizer"
            )
        execution_attempt_id = ""
        explicit_attempt_authority_digest = (
            execution_attempt_authority_digest
        )
        if explicit_attempt_authority_digest:
            if not execution_seal_id:
                raise RuntimeError(
                    "execution attempt authority requires execution seal"
                )
            if len(explicit_attempt_authority_digest) != 64:
                raise ValueError(
                    "execution_attempt_authority_digest must be SHA-256 hex"
                )
            # Opaque 64-character attempt authority digest.
            explicit_attempt_authority_digest = (
                explicit_attempt_authority_digest.lower()
            )
            execution_attempt_id = execution_seal_id
        execution_attempt_authority_digest = (
            explicit_attempt_authority_digest
        )
        execution_attempt_state = ""
        if execution_attempt is not None:
            if not isinstance(execution_attempt, AIExecutionAttempt):
                raise TypeError("execution_attempt must be AIExecutionAttempt")
            if not execution_seal_id:
                execution_seal_id = execution_attempt.execution_seal_id
            if execution_attempt.session_id != session.session_id:
                raise RuntimeError(
                    "execution attempt session differs from finalized session"
                )
            if execution_attempt.plan_fingerprint != execution.report.fingerprint:
                raise RuntimeError(
                    "execution attempt plan differs from finalized execution"
                )
            if execution_seal_id and (
                execution_attempt.execution_seal_id != execution_seal_id
            ):
                raise RuntimeError(
                    "execution attempt seal differs from finalizer seal"
                )
            if (
                execution_attempt.execution_backend_id
                and execution_attempt.execution_backend_id
                != execution.provenance.execution_backend_id
            ):
                raise RuntimeError(
                    "execution attempt backend differs from execution provenance"
                )
            if runtime_trust_digest and (
                execution_attempt.runtime_trust_digest
                != runtime_trust_digest
            ):
                raise RuntimeError(
                    "execution attempt runtime trust differs from finalizer"
                )
            if release_evidence_digest and (
                execution_attempt.release_evidence_digest
                != release_evidence_digest
            ):
                raise RuntimeError(
                    "execution attempt release evidence differs from finalizer"
                )
            if session.phase.value == "complete":
                if execution_attempt.state is not ExecutionAttemptState.SUCCEEDED:
                    raise RuntimeError(
                        "completed session requires successful execution attempt"
                    )
                if (
                    execution_attempt.terminal_evidence_digest
                    != execution.provenance.digest
                ):
                    raise RuntimeError(
                        "execution attempt terminal evidence differs from provenance"
                    )
            elif session.phase.value == "failed":
                if execution_attempt.state is not ExecutionAttemptState.FAILED:
                    raise RuntimeError(
                        "failed session requires failed execution attempt"
                    )
                if (
                    execution_attempt.terminal_evidence_digest
                    and execution_attempt.terminal_evidence_digest
                    != execution.provenance.digest
                ):
                    raise RuntimeError(
                        "execution attempt terminal evidence differs from provenance"
                    )
            if (
                explicit_attempt_authority_digest
                and explicit_attempt_authority_digest
                != execution_attempt.authority_digest
            ):
                raise RuntimeError(
                    "execution attempt authority differs from finalizer authority"
                )
            execution_attempt_id = execution_attempt.attempt_id
            execution_attempt_authority_digest = (
                execution_attempt.authority_digest
            )
            execution_attempt_state = execution_attempt.state.value

        finalization = None
        if self.finalizations is not None:
            stored_finalization = self.finalizations.reserve(
                session_id=session.session_id,
                provenance_digest=execution.provenance.digest,
                execution_attempt_id=execution_attempt_id,
                execution_attempt_authority_digest=(
                    execution_attempt_authority_digest
                ),
                runtime_trust_digest=runtime_trust_digest,
                release_evidence_digest=release_evidence_digest,
                require_recovery_checkpoint=(
                    self.recovery_checkpoints is not None
                ),
                require_witness=(self.audit_witnesses is not None),
                require_signed_evidence=(
                    self.execution_evidence is not None
                ),
            )
            finalization = stored_finalization.finalization

        finalization_id = (
            finalization.finalization_id
            if finalization is not None
            else AIExecutionFinalization.derive_id(
                session_id=session.session_id,
                provenance_digest=execution.provenance.digest,
                execution_attempt_id=execution_attempt_id,
            )
        )

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
        if self.finalizations is not None and finalization is not None:
            finalization = self.finalizations.advance(
                finalization,
                FinalizationPhase.SESSION_EVIDENCE,
                session_evidence_digest=evidence.digest,
            ).finalization

        session_journal = SessionJournalEvidence.from_journal(
            self.journal,
            session.session_id,
        )
        session_integrity = self.integrity_verifier.require(
            session_journal,
            evidence,
        )
        root_protections = None
        root_protection_digest = ""
        if self.root_protection_store is not None:
            root_protections = (
                self.root_protection_store.protect_finalization(
                    finalization_id=finalization_id,
                    source_digest=execution.provenance.digest,
                    journal_chain_id=self.journal_chain_id,
                    journal_root=session_integrity.journal_root,
                    receipt_chain_id=self.receipt_chain_id,
                    receipt_root=session_integrity.receipt_root,
                )
            )
            root_protection_digest = root_protections.digest
        session_journal_commit = None
        session_journal_manifest_digest = ""
        if self.session_journals is not None:
            session_journal_commit = self.session_journals.put(
                finalization_id=finalization_id,
                journal_root=session_integrity.journal_root,
                journal_evidence=session_journal,
            )
            session_journal_manifest_digest = (
                session_journal_commit.stored.manifest.digest
            )
            if (
                session_journal_commit.stored.manifest.journal_digest
                != session_journal.digest
            ):
                raise RuntimeError(
                    "stored durable session journal differs from final evidence"
                )
        checkpoint = AISessionCheckpoint.capture(
            session,
            journal_root=session_integrity.journal_root,
            receipt_root=session_integrity.receipt_root,
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
            runtime_trust_digest=runtime_trust_digest,
            authority_health_policy_digest=authority_health_policy_digest,
            execution_attempt_id=execution_attempt_id,
            execution_attempt_authority_digest=(
                execution_attempt_authority_digest
            ),
            session_integrity_digest=session_integrity.digest,
            session_journal_manifest_digest=(
                session_journal_manifest_digest
            ),
            root_protection_digest=(
                root_protection_digest
            ),
        )
        recovery_commit = None
        if self.recovery_checkpoints is not None:
            recovery_commit = self.recovery_checkpoints.put(
                finalization_id,
                recovery,
            )
            if (
                recovery_commit.stored.record.checkpoint.digest
                != recovery.digest
            ):
                raise RuntimeError(
                    "stored recovery checkpoint differs from final evidence"
                )
        if self.finalizations is not None and finalization is not None:
            finalization = self.finalizations.advance(
                finalization,
                FinalizationPhase.CHECKPOINTED,
                session_evidence_digest=evidence.digest,
                recovery_checkpoint_digest=recovery.digest,
            ).finalization
        anchor_args = {
            "session_id": session.session_id,
            "checkpoint_digest": recovery.digest,
            "provenance_digest": execution.provenance.digest,
            "journal_root": checkpoint.journal_root,
            "receipt_root": checkpoint.receipt_root,
            "session_evidence_digest": evidence.digest,
            "release_evidence_digest": release_evidence_digest,
            "sandbox_binding_digest": sandbox_binding_digest,
            "runtime_trust_digest": runtime_trust_digest,
            "authority_health_policy_digest": (
                authority_health_policy_digest
            ),
            "execution_attempt_id": execution_attempt_id,
            "execution_attempt_authority_digest": (
                execution_attempt_authority_digest
            ),
        }
        if self.finalizations is not None and finalization is not None:
            anchor = self.audit_anchors.append_once(
                finalization_id=finalization.finalization_id,
                **anchor_args,
            )
        else:
            anchor = self.audit_anchors.append(**anchor_args)
        if not self.audit_anchors.verify():
            raise RuntimeError("AI audit anchor chain failed verification after append")
        audit_root = (
            finalization.audit_root
            if finalization is not None and finalization.audit_root
            else self.audit_anchors.root_hash()
        )
        if self.finalizations is not None and finalization is not None:
            finalization = self.finalizations.advance(
                finalization,
                FinalizationPhase.ANCHORED,
                session_evidence_digest=evidence.digest,
                recovery_checkpoint_digest=recovery.digest,
                audit_anchor_digest=anchor.anchor.digest,
                audit_chain_node_hash=anchor.chain_node_hash,
                audit_root=audit_root,
            ).finalization

        audit_witness = None
        if self.audit_witnesses is not None:
            audit_witness = self.audit_witnesses.publish_once(
                audit_root,
                runtime_trust_digest=runtime_trust_digest,
                release_evidence_digest=release_evidence_digest,
            )
            witness_verification = self.audit_witnesses.verify()
            if not witness_verification.ok:
                raise RuntimeError(
                    "AI audit witness chain failed verification after publish"
                )
            self.audit_witnesses.require_witness(
                audit_witness,
            )
            if self.finalizations is not None and finalization is not None:
                finalization = self.finalizations.advance(
                    finalization,
                    FinalizationPhase.WITNESSED,
                    session_evidence_digest=evidence.digest,
                    recovery_checkpoint_digest=recovery.digest,
                    audit_anchor_digest=anchor.anchor.digest,
                    audit_chain_node_hash=anchor.chain_node_hash,
                    audit_root=audit_root,
                    audit_witness_digest=audit_witness.witness.digest,
                    audit_witness_sequence=audit_witness.witness.sequence,
                ).finalization

        signed_execution_evidence = None
        if self.execution_evidence is not None:
            final_bundle = self.execution_evidence_builder.build(
                session_id=session.session_id,
                intent_fingerprint=session.intent.fingerprint,
                proposal_fingerprint=session.proposal.fingerprint,
                provenance_digest=execution.provenance.digest,
                checkpoint_digest=recovery.digest,
                session_evidence_digest=evidence.digest,
                session_journal_digest=session_journal.digest,
                audit_anchor_digest=anchor.anchor.digest,
                audit_chain_node_hash=anchor.chain_node_hash,
                release_evidence_digest=release_evidence_digest,
                sandbox_binding_digest=sandbox_binding_digest,
                model_attestation_digest=model_attestation_digest,
                execution_seal_id=execution_seal_id,
                quorum_approval_digest=quorum_approval_digest,
                runtime_trust_digest=runtime_trust_digest,
                authority_health_policy_digest=(
                    authority_health_policy_digest
                ),
                execution_attempt_id=execution_attempt_id,
                execution_attempt_authority_digest=(
                    execution_attempt_authority_digest
                ),
                audit_witness_digest=(
                    ""
                    if audit_witness is None
                    else audit_witness.witness.digest
                ),
                audit_witness_sequence=(
                    None
                    if audit_witness is None
                    else audit_witness.witness.sequence
                ),
                execution_attempt_state=execution_attempt_state,
                session_integrity_digest=session_integrity.digest,
                session_journal_manifest_digest=(
                    session_journal_manifest_digest
                ),
                root_protection_digest=(
                    root_protection_digest
                ),
            )
            signed_execution_evidence = self.execution_evidence.append_once(
                final_bundle
            )
            if not self.execution_evidence.verify():
                raise RuntimeError(
                    "AI execution evidence chain failed verification after append"
                )
            if self.finalizations is not None and finalization is not None:
                finalization = self.finalizations.advance(
                    finalization,
                    FinalizationPhase.SIGNED,
                    session_evidence_digest=evidence.digest,
                    recovery_checkpoint_digest=recovery.digest,
                    audit_anchor_digest=anchor.anchor.digest,
                    audit_chain_node_hash=anchor.chain_node_hash,
                    audit_root=audit_root,
                    audit_witness_digest=(
                        ""
                        if audit_witness is None
                        else audit_witness.witness.digest
                    ),
                    audit_witness_sequence=(
                        None
                        if audit_witness is None
                        else audit_witness.witness.sequence
                    ),
                    execution_evidence_digest=final_bundle.digest,
                    execution_evidence_chain_node_hash=(
                        signed_execution_evidence.chain_node_hash
                    ),
                ).finalization
        if self.finalizations is not None and finalization is not None:
            finalization = self.finalizations.advance(
                finalization,
                FinalizationPhase.COMPLETE,
                session_evidence_digest=evidence.digest,
                recovery_checkpoint_digest=recovery.digest,
                audit_anchor_digest=anchor.anchor.digest,
                audit_chain_node_hash=anchor.chain_node_hash,
                audit_root=audit_root,
                audit_witness_digest=(
                    ""
                    if audit_witness is None
                    else audit_witness.witness.digest
                ),
                audit_witness_sequence=(
                    None
                    if audit_witness is None
                    else audit_witness.witness.sequence
                ),
                execution_evidence_digest=(
                    ""
                    if signed_execution_evidence is None
                    else signed_execution_evidence.evidence.digest
                ),
                execution_evidence_chain_node_hash=(
                    ""
                    if signed_execution_evidence is None
                    else signed_execution_evidence.chain_node_hash
                ),
            ).finalization
        session_commit = None
        if self.session_commits is not None:
            stored_finalization = self.finalizations.current(
                finalization_id
            )
            if stored_finalization is None:
                raise RuntimeError(
                    "complete finalization disappeared before session commit"
                )
            if (
                stored_finalization.finalization.phase
                is not FinalizationPhase.COMPLETE
            ):
                raise RuntimeError(
                    "session commit requires complete finalization"
                )
            commit = self.session_commit_builder.build(
                finalization=stored_finalization.finalization,
                finalization_revision=stored_finalization.revision,
                recovery_checkpoint_digest=recovery.digest,
                recovery_revision=(
                    None
                    if recovery_commit is None
                    else recovery_commit.stored.revision
                ),
                session_evidence_digest=evidence.digest,
                session_evidence_revision=stored.revision,
                session_journal_digest=session_journal.digest,
                session_journal_manifest_digest=(
                    session_journal_manifest_digest
                ),
                session_journal_revision=(
                    None
                    if session_journal_commit is None
                    else session_journal_commit.stored.revision
                ),
                session_integrity_digest=session_integrity.digest,
                journal_root=checkpoint.journal_root,
                receipt_root=checkpoint.receipt_root,
                audit_anchor_digest=anchor.anchor.digest,
                audit_chain_node_hash=anchor.chain_node_hash,
                audit_root=audit_root,
                audit_witness_digest=(
                    ""
                    if audit_witness is None
                    else audit_witness.witness.digest
                ),
                audit_witness_sequence=(
                    None
                    if audit_witness is None
                    else audit_witness.witness.sequence
                ),
                execution_evidence_digest=(
                    ""
                    if signed_execution_evidence is None
                    else signed_execution_evidence.evidence.digest
                ),
                execution_evidence_chain_node_hash=(
                    ""
                    if signed_execution_evidence is None
                    else signed_execution_evidence.chain_node_hash
                ),
                root_protection_digest=(
                    root_protection_digest
                ),
            )
            session_commit = self.session_commits.publish(
                commit
            )
            finalization = stored_finalization.finalization
        return FinalizedAIExecutionEvidence(
            checkpoint,
            recovery,
            evidence,
            session_journal,
            anchor,
            audit_witness,
            signed_execution_evidence,
            finalization,
            recovery_commit,
            session_integrity,
            session_journal_commit,
            session_commit,
            root_protections,
        )
