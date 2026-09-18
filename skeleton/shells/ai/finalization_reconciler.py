"""Verify and reconcile crash-interrupted AI execution finalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore, SignedAIAuditAnchor
from skeleton.shells.ai.audit_witness import (
    AIAuditWitnessStore,
    SignedAIAuditWitness,
)
from skeleton.shells.ai.execution_evidence import (
    AIExecutionEvidenceStore,
    SignedAIExecutionEvidence,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    AIExecutionFinalizationStore,
    ExecutionFinalizationConflict,
    FinalizationPhase,
)
from skeleton.shells.ai.recovery_store import AIRecoveryCheckpointStore
from skeleton.shells.ai.session_evidence import SessionEvidenceStore


class FinalizationReconcileAction(str, Enum):
    COMPLETE = "complete"
    RESUME_FINALIZATION = "resume_finalization"
    MANUAL_REVIEW = "manual_review"


_PHASE_ORDER = {
    FinalizationPhase.STARTED: 0,
    FinalizationPhase.SESSION_EVIDENCE: 10,
    FinalizationPhase.CHECKPOINTED: 20,
    FinalizationPhase.ANCHORED: 30,
    FinalizationPhase.WITNESSED: 40,
    FinalizationPhase.SIGNED: 50,
    FinalizationPhase.COMPLETE: 60,
}


@dataclass(frozen=True)
class FinalizationLayerReport:
    configured: bool
    expected: bool
    present: bool
    verified: bool
    digest: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "expected": self.expected,
            "present": self.present,
            "verified": self.verified,
            "digest": self.digest,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FinalizationReconcileReport:
    finalization_id: str
    phase: FinalizationPhase
    action: FinalizationReconcileAction
    reasons: tuple[str, ...]
    session_evidence: FinalizationLayerReport
    recovery_checkpoint: FinalizationLayerReport
    audit_anchor: FinalizationLayerReport
    audit_witness: FinalizationLayerReport
    execution_evidence: FinalizationLayerReport

    @property
    def ok(self) -> bool:
        return self.action is FinalizationReconcileAction.COMPLETE

    @property
    def safe_to_resume(self) -> bool:
        return self.action is FinalizationReconcileAction.RESUME_FINALIZATION

    def to_dict(self) -> dict[str, object]:
        return {
            "finalization_id": self.finalization_id,
            "phase": self.phase.value,
            "action": self.action.value,
            "ok": self.ok,
            "safe_to_resume": self.safe_to_resume,
            "reasons": list(self.reasons),
            "session_evidence": self.session_evidence.to_dict(),
            "recovery_checkpoint": self.recovery_checkpoint.to_dict(),
            "audit_anchor": self.audit_anchor.to_dict(),
            "audit_witness": self.audit_witness.to_dict(),
            "execution_evidence": self.execution_evidence.to_dict(),
        }


class AIExecutionFinalizationReconciler:
    """Cross-check durable finalization layers after process restart.

    Missing evidence can mean an interrupted finalizer and is resumable while
    conflicting/tampered evidence requires manual review.  Reconciliation may
    fast-forward the state record only when an existing durable artifact proves
    the exact digest already bound by the finalization.
    """

    def __init__(
        self,
        *,
        finalizations: AIExecutionFinalizationStore,
        session_evidence: SessionEvidenceStore,
        audit_anchors: AIAuditAnchorStore,
        recovery_checkpoints: AIRecoveryCheckpointStore | None = None,
        audit_witnesses: AIAuditWitnessStore | None = None,
        execution_evidence: AIExecutionEvidenceStore | None = None,
    ) -> None:
        self.finalizations = finalizations
        self.session_evidence = session_evidence
        self.audit_anchors = audit_anchors
        self.recovery_checkpoints = recovery_checkpoints
        self.audit_witnesses = audit_witnesses
        self.execution_evidence = execution_evidence

    @staticmethod
    def _phase_at_least(
        item: AIExecutionFinalization,
        phase: FinalizationPhase,
    ) -> bool:
        return _PHASE_ORDER[item.phase] >= _PHASE_ORDER[phase]

    def _session_report(
        self,
        item: AIExecutionFinalization,
    ) -> FinalizationLayerReport:
        expected = self._phase_at_least(
            item,
            FinalizationPhase.SESSION_EVIDENCE,
        )
        stored = self.session_evidence.current(item.session_id)
        if stored is None:
            return FinalizationLayerReport(
                True,
                expected,
                False,
                not expected,
                reason=(
                    "session execution evidence is missing"
                    if expected
                    else ""
                ),
            )
        digest = stored.evidence.digest
        if item.session_evidence_digest:
            verified = digest == item.session_evidence_digest
            return FinalizationLayerReport(
                True,
                expected,
                True,
                verified,
                digest,
                "" if verified else "session evidence digest mismatch",
            )
        return FinalizationLayerReport(
            True,
            expected,
            True,
            not expected,
            digest,
            (
                "session evidence exists before finalization record binds it"
                if expected
                else ""
            ),
        )

    def _recovery_report(
        self,
        item: AIExecutionFinalization,
    ) -> FinalizationLayerReport:
        configured = self.recovery_checkpoints is not None
        expected = (
            item.require_recovery_checkpoint
            or self._phase_at_least(
                item,
                FinalizationPhase.CHECKPOINTED,
            )
        )
        if not configured:
            return FinalizationLayerReport(
                False,
                expected,
                False,
                not item.require_recovery_checkpoint,
                reason=(
                    "required recovery checkpoint store is unavailable"
                    if item.require_recovery_checkpoint
                    else ""
                ),
            )
        stored = self.recovery_checkpoints.get(
            item.finalization_id
        )
        if stored is None:
            return FinalizationLayerReport(
                True,
                expected,
                False,
                not expected,
                reason=(
                    "recovery checkpoint is missing"
                    if expected
                    else ""
                ),
            )
        digest = stored.record.checkpoint.digest
        if item.recovery_checkpoint_digest:
            verified = digest == item.recovery_checkpoint_digest
            return FinalizationLayerReport(
                True,
                expected,
                True,
                verified,
                digest,
                "" if verified else "recovery checkpoint digest mismatch",
            )
        return FinalizationLayerReport(
            True,
            expected,
            True,
            False,
            digest,
            "recovery checkpoint exists before state binds its digest",
        )

    def _anchor(
        self,
        item: AIExecutionFinalization,
    ) -> tuple[FinalizationLayerReport, SignedAIAuditAnchor | None]:
        expected = self._phase_at_least(
            item,
            FinalizationPhase.ANCHORED,
        )
        existing = self.audit_anchors.find_by_finalization_id(
            item.finalization_id
        )
        if existing is None:
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    False,
                    not expected,
                    reason=(
                        "audit anchor is missing"
                        if expected
                        else ""
                    ),
                ),
                None,
            )
        if not self.audit_anchors.verify():
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    True,
                    False,
                    existing.anchor.digest,
                    "audit anchor chain integrity failure",
                ),
                existing,
            )

        verified = True
        reason = ""
        if item.audit_anchor_digest and (
            existing.anchor.digest != item.audit_anchor_digest
        ):
            verified = False
            reason = "audit anchor digest mismatch"
        elif item.audit_chain_node_hash and (
            existing.chain_node_hash != item.audit_chain_node_hash
        ):
            verified = False
            reason = "audit anchor chain node mismatch"
        elif (
            existing.anchor.provenance_digest
            != item.provenance_digest
        ):
            verified = False
            reason = "audit anchor provenance binding mismatch"
        elif (
            existing.anchor.execution_attempt_id
            != item.execution_attempt_id
        ):
            verified = False
            reason = "audit anchor execution attempt mismatch"
        elif (
            existing.anchor.execution_attempt_authority_digest
            != item.execution_attempt_authority_digest
        ):
            verified = False
            reason = "audit anchor attempt authority mismatch"

        return (
            FinalizationLayerReport(
                True,
                expected,
                True,
                verified,
                existing.anchor.digest,
                reason,
            ),
            existing,
        )

    def _witness(
        self,
        item: AIExecutionFinalization,
    ) -> tuple[FinalizationLayerReport, SignedAIAuditWitness | None]:
        configured = self.audit_witnesses is not None
        expected = item.require_witness or self._phase_at_least(
            item,
            FinalizationPhase.WITNESSED,
        )
        if not configured:
            return (
                FinalizationLayerReport(
                    False,
                    expected,
                    False,
                    not item.require_witness,
                    reason=(
                        "required audit witness store is unavailable"
                        if item.require_witness
                        else ""
                    ),
                ),
                None,
            )
        if not item.audit_root:
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    False,
                    not expected,
                    reason=(
                        "finalization does not bind an audit root"
                        if expected
                        else ""
                    ),
                ),
                None,
            )
        existing = self.audit_witnesses.find(
            item.audit_root,
            runtime_trust_digest=item.runtime_trust_digest,
            release_evidence_digest=item.release_evidence_digest,
        )
        if existing is None:
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    False,
                    not expected,
                    reason=(
                        "audit witness is missing"
                        if expected
                        else ""
                    ),
                ),
                None,
            )
        try:
            canonical = self.audit_witnesses.require_witness(
                existing
            )
        except RuntimeError as exc:
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    True,
                    False,
                    existing.witness.digest,
                    str(exc),
                ),
                existing,
            )
        verified = True
        reason = ""
        if item.audit_witness_digest and (
            canonical.witness.digest != item.audit_witness_digest
        ):
            verified = False
            reason = "audit witness digest mismatch"
        elif (
            item.audit_witness_sequence is not None
            and canonical.witness.sequence
            != item.audit_witness_sequence
        ):
            verified = False
            reason = "audit witness sequence mismatch"
        return (
            FinalizationLayerReport(
                True,
                expected,
                True,
                verified,
                canonical.witness.digest,
                reason,
            ),
            canonical,
        )

    def _signed_execution(
        self,
        item: AIExecutionFinalization,
    ) -> tuple[
        FinalizationLayerReport,
        SignedAIExecutionEvidence | None,
    ]:
        configured = self.execution_evidence is not None
        expected = (
            item.require_signed_evidence
            or self._phase_at_least(
                item,
                FinalizationPhase.SIGNED,
            )
        )
        if not configured:
            return (
                FinalizationLayerReport(
                    False,
                    expected,
                    False,
                    not item.require_signed_evidence,
                    reason=(
                        "required signed execution evidence store is unavailable"
                        if item.require_signed_evidence
                        else ""
                    ),
                ),
                None,
            )
        existing = None
        if item.execution_attempt_id:
            existing = self.execution_evidence.find_by_attempt_id(
                item.execution_attempt_id
            )
        elif item.execution_evidence_digest:
            existing = self.execution_evidence.find_by_digest(
                item.execution_evidence_digest
            )
        if existing is None:
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    False,
                    not expected,
                    reason=(
                        "signed execution evidence is missing"
                        if expected
                        else ""
                    ),
                ),
                None,
            )
        if not self.execution_evidence.verify():
            return (
                FinalizationLayerReport(
                    True,
                    expected,
                    True,
                    False,
                    existing.evidence.digest,
                    "signed execution evidence chain integrity failure",
                ),
                existing,
            )
        verified = True
        reason = ""
        if item.execution_evidence_digest and (
            existing.evidence.digest
            != item.execution_evidence_digest
        ):
            verified = False
            reason = "signed execution evidence digest mismatch"
        elif item.execution_evidence_chain_node_hash and (
            existing.chain_node_hash
            != item.execution_evidence_chain_node_hash
        ):
            verified = False
            reason = "signed execution evidence node mismatch"
        elif (
            existing.evidence.provenance_digest
            != item.provenance_digest
        ):
            verified = False
            reason = "signed execution evidence provenance mismatch"
        return (
            FinalizationLayerReport(
                True,
                expected,
                True,
                verified,
                existing.evidence.digest,
                reason,
            ),
            existing,
        )

    @staticmethod
    def _classify(
        item: AIExecutionFinalization,
        layers: tuple[FinalizationLayerReport, ...],
    ) -> tuple[FinalizationReconcileAction, tuple[str, ...]]:
        reasons = tuple(
            layer.reason
            for layer in layers
            if layer.reason
        )
        mismatches = tuple(
            layer
            for layer in layers
            if layer.present and not layer.verified
        )
        unavailable_required = tuple(
            layer
            for layer in layers
            if layer.expected
            and not layer.present
            and not layer.configured
        )
        if mismatches or unavailable_required:
            return (
                FinalizationReconcileAction.MANUAL_REVIEW,
                reasons,
            )
        missing = tuple(
            layer
            for layer in layers
            if layer.expected and not layer.present
        )
        if item.phase is FinalizationPhase.COMPLETE and not missing:
            return (
                FinalizationReconcileAction.COMPLETE,
                reasons,
            )
        return (
            FinalizationReconcileAction.RESUME_FINALIZATION,
            reasons,
        )

    def inspect(
        self,
        finalization_id: str,
    ) -> FinalizationReconcileReport:
        stored = self.finalizations.current(finalization_id)
        if stored is None:
            raise ExecutionFinalizationConflict(
                "finalization record is missing"
            )
        item = stored.finalization
        session_report = self._session_report(item)
        recovery_report = self._recovery_report(item)
        anchor_report, _ = self._anchor(item)
        witness_report, _ = self._witness(item)
        signed_report, _ = self._signed_execution(item)
        layers = (
            session_report,
            recovery_report,
            anchor_report,
            witness_report,
            signed_report,
        )
        action, reasons = self._classify(item, layers)
        return FinalizationReconcileReport(
            item.finalization_id,
            item.phase,
            action,
            reasons,
            session_report,
            recovery_report,
            anchor_report,
            witness_report,
            signed_report,
        )

    def reconcile(
        self,
        finalization_id: str,
    ) -> FinalizationReconcileReport:
        stored = self.finalizations.current(finalization_id)
        if stored is None:
            raise ExecutionFinalizationConflict(
                "finalization record is missing"
            )
        item = stored.finalization

        session_report = self._session_report(item)
        if session_report.present and session_report.verified:
            item = self.finalizations.advance(
                item,
                FinalizationPhase.SESSION_EVIDENCE,
                session_evidence_digest=session_report.digest,
            ).finalization

        recovery_report = self._recovery_report(item)
        if recovery_report.present and recovery_report.verified:
            item = self.finalizations.advance(
                item,
                FinalizationPhase.CHECKPOINTED,
                session_evidence_digest=item.session_evidence_digest,
                recovery_checkpoint_digest=recovery_report.digest,
            ).finalization

        anchor_report, anchor = self._anchor(item)
        if (
            anchor is not None
            and anchor_report.verified
        ):
            audit_root = item.audit_root
            if not audit_root and (
                self.audit_anchors.root_hash()
                == anchor.chain_node_hash
            ):
                audit_root = anchor.chain_node_hash
            if audit_root:
                item = self.finalizations.advance(
                    item,
                    FinalizationPhase.ANCHORED,
                    session_evidence_digest=(
                        item.session_evidence_digest
                    ),
                    recovery_checkpoint_digest=(
                        item.recovery_checkpoint_digest
                    ),
                    audit_anchor_digest=anchor.anchor.digest,
                    audit_chain_node_hash=anchor.chain_node_hash,
                    audit_root=audit_root,
                ).finalization

        witness_report, witness = self._witness(item)
        if witness is not None and witness_report.verified:
            item = self.finalizations.advance(
                item,
                FinalizationPhase.WITNESSED,
                session_evidence_digest=item.session_evidence_digest,
                recovery_checkpoint_digest=(
                    item.recovery_checkpoint_digest
                ),
                audit_anchor_digest=item.audit_anchor_digest,
                audit_chain_node_hash=item.audit_chain_node_hash,
                audit_root=item.audit_root,
                audit_witness_digest=witness.witness.digest,
                audit_witness_sequence=witness.witness.sequence,
            ).finalization

        signed_report, signed = self._signed_execution(item)
        if signed is not None and signed_report.verified:
            item = self.finalizations.advance(
                item,
                FinalizationPhase.SIGNED,
                session_evidence_digest=item.session_evidence_digest,
                recovery_checkpoint_digest=(
                    item.recovery_checkpoint_digest
                ),
                audit_anchor_digest=item.audit_anchor_digest,
                audit_chain_node_hash=item.audit_chain_node_hash,
                audit_root=item.audit_root,
                audit_witness_digest=item.audit_witness_digest,
                audit_witness_sequence=item.audit_witness_sequence,
                execution_evidence_digest=signed.evidence.digest,
                execution_evidence_chain_node_hash=(
                    signed.chain_node_hash
                ),
            ).finalization

        report = self.inspect(item.finalization_id)
        if (
            report.action
            is FinalizationReconcileAction.RESUME_FINALIZATION
        ):
            required_ready = (
                report.session_evidence.verified
                and report.audit_anchor.verified
                and (
                    not item.require_recovery_checkpoint
                    or report.recovery_checkpoint.verified
                )
                and (
                    not item.require_witness
                    or report.audit_witness.verified
                )
                and (
                    not item.require_signed_evidence
                    or report.execution_evidence.verified
                )
            )
            if required_ready:
                item = self.finalizations.advance(
                    item,
                    FinalizationPhase.COMPLETE,
                    session_evidence_digest=item.session_evidence_digest,
                    recovery_checkpoint_digest=(
                        item.recovery_checkpoint_digest
                    ),
                    audit_anchor_digest=item.audit_anchor_digest,
                    audit_chain_node_hash=item.audit_chain_node_hash,
                    audit_root=item.audit_root,
                    audit_witness_digest=item.audit_witness_digest,
                    audit_witness_sequence=item.audit_witness_sequence,
                    execution_evidence_digest=(
                        item.execution_evidence_digest
                    ),
                    execution_evidence_chain_node_hash=(
                        item.execution_evidence_chain_node_hash
                    ),
                ).finalization
                return self.inspect(item.finalization_id)
        return report
