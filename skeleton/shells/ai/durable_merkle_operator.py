"""Operator workflow for building and verifying finalized-session Merkle proofs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.durable_merkle_session import (
    DurableSessionMerkleAuthority,
    DurableSessionMerkleProofBundle,
    DurableSessionMerkleVerification,
)
from skeleton.shells.ai.durable_merkle_store import (
    DurableMerkleBundleCommit,
    DurableMerkleBundleStoreError,
    DurableSessionMerkleBundleStore,
)
from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalizationStore,
)
from skeleton.shells.ai.recovery_store import (
    AIRecoveryCheckpointStore,
)
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvent,
    SessionJournalEvidence,
)


class DurableMerkleOperatorStatus(
    str,
    Enum,
):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    MANUAL_REVIEW = "manual_review"
    MISSING = "missing"


@dataclass(frozen=True)
class DurableMerkleOperatorResult:
    finalization_id: str
    session_id: str
    status: DurableMerkleOperatorStatus
    bundle_digest: str
    bundle_revision: int | None
    bundle_created: bool
    index_created: bool
    recovery_report_digest: str
    journal_proof_count: int
    receipt_proof_count: int
    verification: (
        DurableSessionMerkleVerification
        | None
    )
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.finalization_id
            or len(self.finalization_id) > 256
        ):
            raise ValueError(
                "invalid Merkle operator finalization_id"
            )
        if len(self.session_id) > 160:
            raise ValueError(
                "Merkle operator session_id too long"
            )
        object.__setattr__(
            self,
            "status",
            DurableMerkleOperatorStatus(
                self.status
            ),
        )
        for name in (
            "bundle_digest",
            "recovery_report_digest",
        ):
            value = getattr(
                self,
                name,
            )
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be SHA-256 hex"
                )
        if self.bundle_revision is not None and (
            isinstance(
                self.bundle_revision,
                bool,
            )
            or not isinstance(
                self.bundle_revision,
                int,
            )
            or self.bundle_revision <= 0
        ):
            raise ValueError(
                "bundle_revision must be positive integer"
            )
        for name in (
            "bundle_created",
            "index_created",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        for name in (
            "journal_proof_count",
            "receipt_proof_count",
        ):
            value = getattr(
                self,
                name,
            )
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    int,
                )
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if (
            self.verification is not None
            and not isinstance(
                self.verification,
                DurableSessionMerkleVerification,
            )
        ):
            raise TypeError(
                "verification must be DurableSessionMerkleVerification"
            )
        object.__setattr__(
            self,
            "issues",
            tuple(self.issues),
        )

    @property
    def ok(self) -> bool:
        return (
            self.status
            is DurableMerkleOperatorStatus.VERIFIED
            and self.verification is not None
            and self.verification.ok
            and not self.issues
        )

    @property
    def safe_to_resume(self) -> bool:
        return (
            self.status
            is DurableMerkleOperatorStatus.INCOMPLETE
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.status
            is DurableMerkleOperatorStatus.MANUAL_REVIEW
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "finalization_id": (
                self.finalization_id
            ),
            "session_id": self.session_id,
            "status": self.status.value,
            "ok": self.ok,
            "safe_to_resume": (
                self.safe_to_resume
            ),
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "bundle_digest": self.bundle_digest,
            "bundle_revision": (
                self.bundle_revision
            ),
            "bundle_created": (
                self.bundle_created
            ),
            "index_created": (
                self.index_created
            ),
            "recovery_report_digest": (
                self.recovery_report_digest
            ),
            "journal_proof_count": (
                self.journal_proof_count
            ),
            "receipt_proof_count": (
                self.receipt_proof_count
            ),
            "verification": (
                None
                if self.verification is None
                else self.verification.to_dict()
            ),
            "issues": list(self.issues),
        }


class DurableMerkleOperatorError(
    RuntimeError
):
    pass


class DurableSessionMerkleOperator:
    """Prepare and verify compact evidence proofs from a finalization ID."""

    def __init__(
        self,
        *,
        finalizations: AIExecutionFinalizationStore,
        recovery_checkpoints: AIRecoveryCheckpointStore,
        session_evidence: SessionEvidenceStore,
        journal,
        receipt_chain,
        recovery_verifier: DurableSessionRecoveryVerifier,
        merkle_authority: DurableSessionMerkleAuthority,
        bundle_store: DurableSessionMerkleBundleStore,
    ) -> None:
        if not isinstance(
            finalizations,
            AIExecutionFinalizationStore,
        ):
            raise TypeError(
                "finalizations must be AIExecutionFinalizationStore"
            )
        if not isinstance(
            recovery_checkpoints,
            AIRecoveryCheckpointStore,
        ):
            raise TypeError(
                "recovery_checkpoints must be AIRecoveryCheckpointStore"
            )
        if not isinstance(
            session_evidence,
            SessionEvidenceStore,
        ):
            raise TypeError(
                "session_evidence must be SessionEvidenceStore"
            )
        if not isinstance(
            recovery_verifier,
            DurableSessionRecoveryVerifier,
        ):
            raise TypeError(
                "recovery_verifier must be DurableSessionRecoveryVerifier"
            )
        if not isinstance(
            merkle_authority,
            DurableSessionMerkleAuthority,
        ):
            raise TypeError(
                "merkle_authority must be DurableSessionMerkleAuthority"
            )
        if not isinstance(
            bundle_store,
            DurableSessionMerkleBundleStore,
        ):
            raise TypeError(
                "bundle_store must be DurableSessionMerkleBundleStore"
            )
        self.finalizations = finalizations
        self.recovery_checkpoints = (
            recovery_checkpoints
        )
        self.session_evidence = session_evidence
        self.journal = journal
        self.receipt_chain = receipt_chain
        self.recovery_verifier = (
            recovery_verifier
        )
        self.merkle_authority = (
            merkle_authority
        )
        self.bundle_store = bundle_store

    def _session_journal(
        self,
        session_id: str,
        root_hash: str,
    ) -> SessionJournalEvidence:
        events_for_session = getattr(
            self.journal,
            "events_for_session",
            None,
        )
        if callable(events_for_session):
            try:
                events = events_for_session(
                    session_id,
                    root_hash=root_hash,
                )
            except TypeError:
                events = None
            else:
                return SessionJournalEvidence(
                    session_id,
                    tuple(
                        SessionJournalEvent(
                            event.sequence,
                            event.event_hash,
                            event.kind,
                            event.proposal_id,
                        )
                        for event in events
                    ),
                )

        snapshot_at = getattr(
            self.journal,
            "snapshot_at",
            None,
        )
        if not callable(snapshot_at):
            if (
                self.journal.root_hash()
                != root_hash
            ):
                raise DurableMerkleOperatorError(
                    "journal cannot reconstruct historical recovery root"
                )
            snapshot = self.journal.snapshot()
        else:
            snapshot = snapshot_at(
                root_hash
            )

        return SessionJournalEvidence(
            session_id,
            tuple(
                SessionJournalEvent(
                    event.sequence,
                    event.event_hash,
                    event.kind,
                    event.proposal_id,
                )
                for event in snapshot
                if event.session_id
                == session_id
            ),
        )

    @staticmethod
    def _status_for_recovery(
        report: DurableSessionRecoveryReport,
    ) -> DurableMerkleOperatorStatus:
        if (
            report.status
            is DurableRecoveryStatus.VERIFIED
        ):
            return (
                DurableMerkleOperatorStatus.VERIFIED
            )
        if (
            report.status
            is DurableRecoveryStatus.INCOMPLETE
        ):
            return (
                DurableMerkleOperatorStatus.INCOMPLETE
            )
        return (
            DurableMerkleOperatorStatus.MANUAL_REVIEW
        )

    def _incomplete_result(
        self,
        finalization_id: str,
        report: DurableSessionRecoveryReport,
    ) -> DurableMerkleOperatorResult:
        issues = tuple(
            finding.message
            for finding in report.findings
        )
        return DurableMerkleOperatorResult(
            finalization_id,
            report.session_id,
            self._status_for_recovery(
                report
            ),
            "",
            None,
            False,
            False,
            report.digest,
            0,
            0,
            None,
            issues,
        )

    def _inputs(
        self,
        finalization_id: str,
        recovery_report: DurableSessionRecoveryReport,
    ):
        finalization = self.finalizations.current(
            finalization_id
        )
        if finalization is None:
            raise DurableMerkleOperatorError(
                "finalization disappeared after recovery verification"
            )
        recovery = (
            self.recovery_checkpoints.get(
                finalization_id
            )
        )
        if recovery is None:
            raise DurableMerkleOperatorError(
                "recovery checkpoint disappeared after verification"
            )
        session = self.session_evidence.current(
            finalization.finalization.session_id
        )
        if session is None:
            raise DurableMerkleOperatorError(
                "session evidence disappeared after verification"
            )
        integrity = recovery_report.integrity
        if integrity is None or not integrity.ok:
            raise DurableMerkleOperatorError(
                "verified recovery report lacks valid session integrity proof"
            )
        session_journal = (
            self._session_journal(
                finalization.finalization.session_id,
                recovery.record.checkpoint.session.journal_root,
            )
        )
        return (
            finalization.finalization,
            recovery.record.checkpoint,
            session.evidence,
            integrity,
            session_journal,
        )

    def _verify_bundle(
        self,
        bundle: DurableSessionMerkleProofBundle,
        *,
        finalization_id: str,
        recovery_report: DurableSessionRecoveryReport,
    ) -> DurableSessionMerkleVerification:
        (
            finalization,
            recovery,
            session_evidence,
            integrity,
            session_journal,
        ) = self._inputs(
            finalization_id,
            recovery_report,
        )
        return self.merkle_authority.require(
            bundle,
            finalization_id=(
                finalization_id
            ),
            session_id=(
                finalization.session_id
            ),
            recovery=recovery,
            integrity=integrity,
            session_journal=session_journal,
            session_evidence=session_evidence,
            journal_chain=self.journal,
            receipt_chain=self.receipt_chain,
        )

    def inspect(
        self,
        finalization_id: str,
    ) -> DurableMerkleOperatorResult:
        recovery_report = (
            self.recovery_verifier.verify(
                finalization_id
            )
        )
        if not recovery_report.ok:
            return self._incomplete_result(
                finalization_id,
                recovery_report,
            )

        try:
            stored = (
                self.bundle_store
                .get_by_finalization(
                    finalization_id
                )
            )
        except DurableMerkleBundleStoreError as exc:
            return DurableMerkleOperatorResult(
                finalization_id,
                recovery_report.session_id,
                DurableMerkleOperatorStatus.MANUAL_REVIEW,
                "",
                None,
                False,
                False,
                recovery_report.digest,
                0,
                0,
                None,
                (
                    "stored Merkle bundle state is inconsistent: "
                    f"{type(exc).__name__}",
                ),
            )
        if stored is None:
            return DurableMerkleOperatorResult(
                finalization_id,
                recovery_report.session_id,
                DurableMerkleOperatorStatus.MISSING,
                "",
                None,
                False,
                False,
                recovery_report.digest,
                0,
                0,
                None,
                (
                    "Merkle proof bundle has not been prepared",
                ),
            )

        try:
            verification = (
                self._verify_bundle(
                    stored.bundle,
                    finalization_id=(
                        finalization_id
                    ),
                    recovery_report=(
                        recovery_report
                    ),
                )
            )
        except Exception as exc:
            return DurableMerkleOperatorResult(
                finalization_id,
                recovery_report.session_id,
                DurableMerkleOperatorStatus.MANUAL_REVIEW,
                stored.bundle.digest,
                stored.revision,
                False,
                False,
                recovery_report.digest,
                len(
                    stored.bundle
                    .journal_proofs
                ),
                len(
                    stored.bundle
                    .receipt_proofs
                ),
                None,
                (
                    "stored Merkle bundle verification failed: "
                    f"{type(exc).__name__}",
                ),
            )

        return DurableMerkleOperatorResult(
            finalization_id,
            recovery_report.session_id,
            DurableMerkleOperatorStatus.VERIFIED,
            stored.bundle.digest,
            stored.revision,
            False,
            False,
            recovery_report.digest,
            len(
                stored.bundle
                .journal_proofs
            ),
            len(
                stored.bundle
                .receipt_proofs
            ),
            verification,
            (),
        )

    def prepare(
        self,
        finalization_id: str,
    ) -> DurableMerkleOperatorResult:
        recovery_report = (
            self.recovery_verifier.verify(
                finalization_id
            )
        )
        if not recovery_report.ok:
            return self._incomplete_result(
                finalization_id,
                recovery_report,
            )

        (
            finalization,
            recovery,
            session_evidence,
            integrity,
            session_journal,
        ) = self._inputs(
            finalization_id,
            recovery_report,
        )
        bundle = (
            self.merkle_authority.build(
                finalization_id=(
                    finalization_id
                ),
                session_id=(
                    finalization.session_id
                ),
                recovery=recovery,
                integrity=integrity,
                session_journal=(
                    session_journal
                ),
                session_evidence=(
                    session_evidence
                ),
                journal_chain=self.journal,
                receipt_chain=(
                    self.receipt_chain
                ),
            )
        )
        commit: DurableMerkleBundleCommit = (
            self.bundle_store.put_once(
                bundle
            )
        )
        verification = (
            self._verify_bundle(
                commit.stored.bundle,
                finalization_id=(
                    finalization_id
                ),
                recovery_report=(
                    recovery_report
                ),
            )
        )
        return DurableMerkleOperatorResult(
            finalization_id,
            finalization.session_id,
            DurableMerkleOperatorStatus.VERIFIED,
            commit.stored.bundle.digest,
            commit.stored.revision,
            commit.bundle_created,
            commit.index_created,
            recovery_report.digest,
            len(
                commit.stored.bundle
                .journal_proofs
            ),
            len(
                commit.stored.bundle
                .receipt_proofs
            ),
            verification,
            (),
        )

    def require(
        self,
        finalization_id: str,
        *,
        prepare_if_missing: bool = False,
    ) -> DurableMerkleOperatorResult:
        if not isinstance(
            prepare_if_missing,
            bool,
        ):
            raise ValueError(
                "prepare_if_missing must be bool"
            )
        report = self.inspect(
            finalization_id
        )
        if (
            report.status
            is DurableMerkleOperatorStatus.MISSING
            and prepare_if_missing
        ):
            report = self.prepare(
                finalization_id
            )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else (
                    "durable Merkle operator "
                    f"is {report.status.value}"
                )
            )
            raise DurableMerkleOperatorError(
                detail
            )
        return report

    def verify_stored(
        self,
        finalization_id: str,
    ) -> DurableMerkleOperatorResult:
        try:
            stored = (
                self.bundle_store
                .require_finalization(
                    finalization_id
                )
            )
        except DurableMerkleBundleStoreError as exc:
            raise DurableMerkleOperatorError(
                str(exc)
            ) from exc

        recovery_report = (
            self.recovery_verifier
            .require_verified(
                finalization_id
            )
        )
        verification = self._verify_bundle(
            stored.bundle,
            finalization_id=(
                finalization_id
            ),
            recovery_report=(
                recovery_report
            ),
        )
        return DurableMerkleOperatorResult(
            finalization_id,
            recovery_report.session_id,
            DurableMerkleOperatorStatus.VERIFIED,
            stored.bundle.digest,
            stored.revision,
            False,
            False,
            recovery_report.digest,
            len(
                stored.bundle.journal_proofs
            ),
            len(
                stored.bundle.receipt_proofs
            ),
            verification,
            (),
        )
