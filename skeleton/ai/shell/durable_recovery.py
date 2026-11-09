"""End-to-end restart verification for durable AI shell execution evidence.

Given only a finalization identifier and durable stores, this verifier rebuilds
one terminal session's evidence at the historical journal/receipt roots captured
by its recovery checkpoint.  It distinguishes missing/incomplete finalization
work from conflicting or corrupted evidence that requires manual review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchiveRepository,
)
from skeleton.shells.ai.durable_proof_window_operator import (
    DurableProofWindowOperator,
)
from skeleton.shells.ai.durable_session_commit import (
    DurableSessionCommitCorruption,
    DurableSessionCommitStore,
    finalization_evidence_digest,
)
from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalStore,
)
from skeleton.shells.ai.execution_evidence import (
    AIExecutionEvidenceStore,
    SignedAIExecutionEvidence,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    AIExecutionFinalizationStore,
    FinalizationPhase,
)
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.recovery_store import (
    AIRecoveryCheckpointStore,
    StoredRecoveryCheckpoint,
)
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
    SessionExecutionEvidence,
)
from skeleton.shells.ai.session_integrity import (
    SessionEvidenceIntegrityError,
    SessionEvidenceIntegrityReport,
    SessionEvidenceIntegrityVerifier,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvent,
    SessionJournalEvidence,
)


class DurableRecoveryStatus(str, Enum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    MANUAL_REVIEW = "manual_review"


class RecoveryFindingSeverity(str, Enum):
    MISSING = "missing"
    CONFLICT = "conflict"
    CORRUPTION = "corruption"


@dataclass(frozen=True)
class DurableRecoveryFinding:
    code: str
    severity: RecoveryFindingSeverity
    message: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 128:
            raise ValueError("invalid recovery finding code")
        object.__setattr__(
            self,
            "severity",
            RecoveryFindingSeverity(
                self.severity
            ),
        )
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid recovery finding message"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class DurableSessionRecoveryReport:
    finalization_id: str
    session_id: str
    status: DurableRecoveryStatus
    finalization_phase: str
    finalization_revision: int | None
    recovery_revision: int | None
    session_evidence_revision: int | None
    finalization_digest: str
    recovery_checkpoint_digest: str
    session_evidence_digest: str
    session_journal_digest: str
    session_integrity_digest: str
    signed_execution_evidence_digest: str
    journal_root: str
    receipt_root: str
    integrity: SessionEvidenceIntegrityReport | None
    findings: tuple[DurableRecoveryFinding, ...]
    session_commit_id: str = ""
    session_commit_digest: str = ""
    session_commit_verified: bool = False

    def __post_init__(self) -> None:
        if not self.finalization_id or len(self.finalization_id) > 256:
            raise ValueError(
                "invalid durable recovery finalization_id"
            )
        if len(self.session_id) > 160:
            raise ValueError(
                "durable recovery session_id too long"
            )
        object.__setattr__(
            self,
            "status",
            DurableRecoveryStatus(
                self.status
            ),
        )
        for name in (
            "finalization_revision",
            "recovery_revision",
            "session_evidence_revision",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive"
                )
        for name in (
            "finalization_digest",
            "recovery_checkpoint_digest",
            "session_evidence_digest",
            "session_journal_digest",
            "session_integrity_digest",
            "signed_execution_evidence_digest",
            "journal_root",
            "receipt_root",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be SHA-256 hex"
                )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def ok(self) -> bool:
        return self.status is DurableRecoveryStatus.VERIFIED

    @property
    def safe_to_resume(self) -> bool:
        return (
            self.status
            is DurableRecoveryStatus.INCOMPLETE
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.status
            is DurableRecoveryStatus.MANUAL_REVIEW
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "finalization_id": self.finalization_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "ok": self.ok,
            "safe_to_resume": self.safe_to_resume,
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "finalization_phase": self.finalization_phase,
            "finalization_revision": (
                self.finalization_revision
            ),
            "recovery_revision": self.recovery_revision,
            "session_evidence_revision": (
                self.session_evidence_revision
            ),
            "finalization_digest": (
                self.finalization_digest
            ),
            "recovery_checkpoint_digest": (
                self.recovery_checkpoint_digest
            ),
            "session_evidence_digest": (
                self.session_evidence_digest
            ),
            "session_journal_digest": (
                self.session_journal_digest
            ),
            "session_integrity_digest": (
                self.session_integrity_digest
            ),
            "signed_execution_evidence_digest": (
                self.signed_execution_evidence_digest
            ),
            "journal_root": self.journal_root,
            "receipt_root": self.receipt_root,
            "integrity": (
                None
                if self.integrity is None
                else self.integrity.to_dict()
            ),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
            "session_commit_id": self.session_commit_id,
            "session_commit_digest": self.session_commit_digest,
            "session_commit_verified": self.session_commit_verified,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableRecoveryVerificationError(RuntimeError):
    pass


class DurableSessionRecoveryVerifier:
    """Reconstruct and verify one finalized execution from durable state."""

    def __init__(
        self,
        *,
        finalizations: AIExecutionFinalizationStore,
        recovery_checkpoints: AIRecoveryCheckpointStore,
        session_evidence: SessionEvidenceStore,
        journal,
        receipt_chain,
        execution_evidence: AIExecutionEvidenceStore | None = None,
        session_journals: DurableSessionJournalStore | None = None,
        journal_archive: DurableArchiveRepository | None = None,
        journal_chain_id: str = "",
        receipt_archive: DurableArchiveRepository | None = None,
        receipt_chain_id: str = "",
        proof_windows: DurableProofWindowOperator | None = None,
        journal_proof_chain_id: str = "",
        receipt_proof_chain_id: str = "",
        session_commits: DurableSessionCommitStore | None = None,
        require_session_commit: bool = False,
    ) -> None:
        if (journal_archive is None) != (not journal_chain_id):
            raise ValueError(
                "journal_archive and journal_chain_id must be configured together"
            )
        if (receipt_archive is None) != (not receipt_chain_id):
            raise ValueError(
                "receipt_archive and receipt_chain_id must be configured together"
            )
        if journal_archive is not None and not isinstance(
            journal_archive,
            DurableArchiveRepository,
        ):
            raise TypeError(
                "journal_archive must be DurableArchiveRepository"
            )
        if receipt_archive is not None and not isinstance(
            receipt_archive,
            DurableArchiveRepository,
        ):
            raise TypeError(
                "receipt_archive must be DurableArchiveRepository"
            )
        if (
            proof_windows is not None
            and not isinstance(
                proof_windows,
                DurableProofWindowOperator,
            )
        ):
            raise TypeError(
                "proof_windows must be DurableProofWindowOperator"
            )
        if proof_windows is None and (
            journal_proof_chain_id
            or receipt_proof_chain_id
        ):
            raise ValueError(
                "proof chain ids require proof_windows operator"
            )
        if proof_windows is not None and (
            not journal_proof_chain_id
            or not receipt_proof_chain_id
        ):
            raise ValueError(
                "journal and receipt proof chain ids are required"
            )
        for name, value in (
            ("journal_proof_chain_id", journal_proof_chain_id),
            ("receipt_proof_chain_id", receipt_proof_chain_id),
        ):
            if value and len(value) > 128:
                raise ValueError(
                    f"{name} too long"
                )

        self.finalizations = finalizations
        self.recovery_checkpoints = recovery_checkpoints
        self.session_evidence = session_evidence
        self.journal = (
            journal
            if journal_archive is None
            else ArchiveBackedHistoricalChain(
                journal_chain_id,
                journal,
                journal_archive,
            )
        )
        self.receipt_chain = (
            receipt_chain
            if receipt_archive is None
            else ArchiveBackedHistoricalChain(
                receipt_chain_id,
                receipt_chain,
                receipt_archive,
            )
        )
        self.execution_evidence = execution_evidence
        if (
            session_commits is not None
            and not isinstance(
                session_commits,
                DurableSessionCommitStore,
            )
        ):
            raise TypeError(
                "session_commits must be DurableSessionCommitStore"
            )
        if not isinstance(require_session_commit, bool):
            raise ValueError(
                "require_session_commit must be bool"
            )
        if (
            require_session_commit
            and session_commits is None
        ):
            raise ValueError(
                "required session commit store is not configured"
            )
        self.session_commits = session_commits
        self.require_session_commit = require_session_commit
        if (
            session_journals is not None
            and not isinstance(
                session_journals,
                DurableSessionJournalStore,
            )
        ):
            raise TypeError(
                "session_journals must be DurableSessionJournalStore"
            )
        self.session_journals = session_journals
        self.journal_archive = journal_archive
        self.journal_chain_id = journal_chain_id
        self.receipt_archive = receipt_archive
        self.receipt_chain_id = receipt_chain_id
        self.proof_windows = proof_windows
        self.journal_proof_chain_id = journal_proof_chain_id
        self.receipt_proof_chain_id = receipt_proof_chain_id
        self.integrity_verifier = SessionEvidenceIntegrityVerifier(
            self.journal,
            self.receipt_chain,
            journal_root_verifier=(
                None
                if proof_windows is None
                else lambda root: proof_windows.verify_root(
                    journal_proof_chain_id,
                    root,
                )
            ),
            receipt_root_verifier=(
                None
                if proof_windows is None
                else lambda root: proof_windows.verify_root(
                    receipt_proof_chain_id,
                    root,
                )
            ),
        )

    @staticmethod
    def _finding(
        findings: list[DurableRecoveryFinding],
        code: str,
        severity: RecoveryFindingSeverity,
        message: str,
    ) -> None:
        findings.append(
            DurableRecoveryFinding(
                code,
                severity,
                message,
            )
        )

    @staticmethod
    def _finalization_digest(
        finalization: AIExecutionFinalization,
    ) -> str:
        raw = json.dumps(
            finalization.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def _session_journal(
        self,
        finalization_id: str,
        session_id: str,
        journal_root: str,
        *,
        expected_digest: str = "",
        expected_manifest_digest: str = "",
    ) -> SessionJournalEvidence:
        if self.session_journals is not None:
            stored = self.session_journals.get(
                finalization_id
            )
            if stored is not None:
                manifest = stored.manifest
                if manifest.session_id != session_id:
                    raise DurableRecoveryVerificationError(
                        "durable session-journal manifest session differs"
                    )
                if manifest.journal_root != journal_root:
                    raise DurableRecoveryVerificationError(
                        "durable session-journal manifest root differs"
                    )
                if (
                    expected_digest
                    and manifest.journal_digest
                    != expected_digest
                ):
                    raise DurableRecoveryVerificationError(
                        "durable session-journal manifest evidence digest differs"
                    )
                if (
                    expected_manifest_digest
                    and manifest.digest
                    != expected_manifest_digest
                ):
                    raise DurableRecoveryVerificationError(
                        "durable session-journal manifest digest differs"
                    )
                return manifest.journal_evidence
            if expected_manifest_digest:
                raise DurableRecoveryVerificationError(
                    "required durable session-journal manifest is missing"
                )

        snapshot_at = getattr(
            self.journal,
            "snapshot_at",
            None,
        )
        if callable(snapshot_at):
            events = snapshot_at(
                journal_root
            )
        else:
            current_root = (
                self.journal.root_hash()
            )
            if current_root != journal_root:
                raise DurableRecoveryVerificationError(
                    "journal cannot resolve historical finalized root"
                )
            events = self.journal.snapshot()
        projected = tuple(
            SessionJournalEvent(
                event.sequence,
                event.event_hash,
                event.kind,
                event.proposal_id,
            )
            for event in events
            if event.session_id == session_id
        )
        evidence = SessionJournalEvidence(
            session_id,
            projected,
        )
        if (
            expected_digest
            and evidence.digest
            != expected_digest
        ):
            raise DurableRecoveryVerificationError(
                "reconstructed session journal differs from expected digest"
            )
        return evidence

    def _signed_evidence(
        self,
        finalization: AIExecutionFinalization,
    ) -> SignedAIExecutionEvidence | None:
        if self.execution_evidence is None:
            return None
        if finalization.execution_attempt_id:
            return (
                self.execution_evidence
                .find_by_attempt_id(
                    finalization.execution_attempt_id
                )
            )
        if finalization.execution_evidence_digest:
            return (
                self.execution_evidence
                .find_by_digest(
                    finalization.execution_evidence_digest
                )
            )
        return None

    @staticmethod
    def _status(
        finalization: AIExecutionFinalization | None,
        findings: tuple[DurableRecoveryFinding, ...],
    ) -> DurableRecoveryStatus:
        if any(
            item.severity
            in {
                RecoveryFindingSeverity.CONFLICT,
                RecoveryFindingSeverity.CORRUPTION,
            }
            for item in findings
        ):
            return DurableRecoveryStatus.MANUAL_REVIEW
        if finalization is None:
            return DurableRecoveryStatus.INCOMPLETE
        if (
            finalization.phase
            is not FinalizationPhase.COMPLETE
        ):
            return DurableRecoveryStatus.INCOMPLETE
        if any(
            item.severity
            is RecoveryFindingSeverity.MISSING
            for item in findings
        ):
            return DurableRecoveryStatus.INCOMPLETE
        return DurableRecoveryStatus.VERIFIED

    def verify(
        self,
        finalization_id: str,
    ) -> DurableSessionRecoveryReport:
        if not finalization_id or len(finalization_id) > 256:
            raise ValueError("invalid finalization_id")
        findings: list[
            DurableRecoveryFinding
        ] = []

        stored_finalization = (
            self.finalizations.current(
                finalization_id
            )
        )
        if stored_finalization is None:
            self._finding(
                findings,
                "finalization.missing",
                RecoveryFindingSeverity.MISSING,
                "finalization record is missing",
            )
            status = self._status(
                None,
                tuple(findings),
            )
            return DurableSessionRecoveryReport(
                finalization_id,
                "",
                status,
                "",
                None,
                None,
                None,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                None,
                tuple(findings),
            )

        finalization = (
            stored_finalization.finalization
        )
        finalization_digest = (
            self._finalization_digest(
                finalization
            )
        )
        session_id = finalization.session_id

        stored_recovery = (
            self.recovery_checkpoints.get(
                finalization_id
            )
        )
        if stored_recovery is None:
            severity = (
                RecoveryFindingSeverity.MISSING
                if finalization.require_recovery_checkpoint
                else RecoveryFindingSeverity.MISSING
            )
            self._finding(
                findings,
                "recovery.missing",
                severity,
                "recovery checkpoint is missing",
            )
            return DurableSessionRecoveryReport(
                finalization_id,
                session_id,
                self._status(
                    finalization,
                    tuple(findings),
                ),
                finalization.phase.value,
                stored_finalization.revision,
                None,
                None,
                finalization_digest,
                "",
                "",
                "",
                "",
                "",
                finalization.audit_root,
                "",
                None,
                tuple(findings),
            )

        recovery = (
            stored_recovery.record.checkpoint
        )
        recovery_digest = recovery.digest
        if (
            finalization.recovery_checkpoint_digest
            and finalization.recovery_checkpoint_digest
            != recovery_digest
        ):
            self._finding(
                findings,
                "recovery.digest_conflict",
                RecoveryFindingSeverity.CONFLICT,
                "finalization recovery checkpoint digest differs from stored checkpoint",
            )
        if (
            stored_recovery.record.session_id
            != session_id
            or recovery.session.session_id
            != session_id
        ):
            self._finding(
                findings,
                "recovery.session_conflict",
                RecoveryFindingSeverity.CONFLICT,
                "recovery checkpoint session differs from finalization",
            )
        if (
            finalization.runtime_trust_digest
            != recovery.runtime_trust_digest
        ):
            self._finding(
                findings,
                "recovery.runtime_trust_conflict",
                RecoveryFindingSeverity.CONFLICT,
                "recovery runtime trust differs from finalization",
            )
        if (
            finalization.release_evidence_digest
            != recovery.release_evidence_digest
        ):
            self._finding(
                findings,
                "recovery.release_conflict",
                RecoveryFindingSeverity.CONFLICT,
                "recovery release evidence differs from finalization",
            )
        if (
            finalization.execution_attempt_id
            != recovery.execution_attempt_id
            or finalization.execution_attempt_authority_digest
            != recovery.execution_attempt_authority_digest
        ):
            self._finding(
                findings,
                "recovery.attempt_conflict",
                RecoveryFindingSeverity.CONFLICT,
                "recovery execution attempt differs from finalization",
            )

        stored_session = (
            self.session_evidence.current(
                session_id
            )
        )
        session_evidence_value: (
            SessionExecutionEvidence | None
        ) = None
        session_evidence_revision = None
        if stored_session is None:
            self._finding(
                findings,
                "session_evidence.missing",
                RecoveryFindingSeverity.MISSING,
                "session execution evidence is missing",
            )
        else:
            session_evidence_value = (
                stored_session.evidence
            )
            session_evidence_revision = (
                stored_session.revision
            )
            if (
                finalization.session_evidence_digest
                and finalization.session_evidence_digest
                != session_evidence_value.digest
            ):
                self._finding(
                    findings,
                    "session_evidence.finalization_conflict",
                    RecoveryFindingSeverity.CONFLICT,
                    "session evidence digest differs from finalization",
                )
            if (
                recovery.session_evidence_digest
                and recovery.session_evidence_digest
                != session_evidence_value.digest
            ):
                self._finding(
                    findings,
                    "session_evidence.recovery_conflict",
                    RecoveryFindingSeverity.CONFLICT,
                    "session evidence digest differs from recovery checkpoint",
                )

        journal_root = (
            recovery.session.journal_root
        )
        receipt_root = (
            recovery.session.receipt_root
        )
        session_journal = None
        session_journal_digest = ""
        try:
            session_journal = (
                self._session_journal(
                    finalization_id,
                    session_id,
                    journal_root,
                    expected_digest=(
                        recovery.session_journal_digest
                    ),
                    expected_manifest_digest=(
                        recovery.session_journal_manifest_digest
                    ),
                )
            )
            session_journal_digest = (
                session_journal.digest
            )
            if (
                recovery.session_journal_digest
                and recovery.session_journal_digest
                != session_journal_digest
            ):
                self._finding(
                    findings,
                    "session_journal.digest_conflict",
                    RecoveryFindingSeverity.CONFLICT,
                    "reconstructed session journal differs from recovery checkpoint",
                )
        except Exception as exc:
            self._finding(
                findings,
                "session_journal.corruption",
                RecoveryFindingSeverity.CORRUPTION,
                "unable to reconstruct historical session journal: "
                f"{type(exc).__name__}",
            )

        integrity_report = None
        if (
            session_journal is not None
            and session_evidence_value is not None
        ):
            try:
                integrity_report = (
                    self.integrity_verifier.require(
                        session_journal,
                        session_evidence_value,
                        expected_journal_root=(
                            journal_root
                        ),
                        expected_receipt_root=(
                            receipt_root
                        ),
                    )
                )
            except SessionEvidenceIntegrityError as exc:
                self._finding(
                    findings,
                    "session_integrity.failed",
                    RecoveryFindingSeverity.CORRUPTION,
                    str(exc),
                )
            except Exception as exc:
                self._finding(
                    findings,
                    "session_integrity.error",
                    RecoveryFindingSeverity.CORRUPTION,
                    "session integrity verification raised "
                    f"{type(exc).__name__}",
                )

        session_integrity_digest = (
            ""
            if integrity_report is None
            else integrity_report.digest
        )
        if (
            integrity_report is not None
            and recovery.session_integrity_digest
            and recovery.session_integrity_digest
            != integrity_report.digest
        ):
            self._finding(
                findings,
                "session_integrity.digest_conflict",
                RecoveryFindingSeverity.CONFLICT,
                "reconstructed session integrity digest differs from recovery checkpoint",
            )

        signed = self._signed_evidence(
            finalization
        )
        signed_digest = ""
        if finalization.require_signed_evidence:
            if self.execution_evidence is None:
                self._finding(
                    findings,
                    "signed_evidence.store_missing",
                    RecoveryFindingSeverity.MISSING,
                    "required signed execution evidence store is unavailable",
                )
            elif signed is None:
                self._finding(
                    findings,
                    "signed_evidence.missing",
                    RecoveryFindingSeverity.MISSING,
                    "required signed execution evidence is missing",
                )

        if (
            self.execution_evidence is not None
            and not self.execution_evidence.verify()
        ):
            self._finding(
                findings,
                "signed_evidence.chain_corruption",
                RecoveryFindingSeverity.CORRUPTION,
                "signed execution evidence chain failed integrity",
            )

        if signed is not None:
            evidence = signed.evidence
            signed_digest = evidence.digest
            checks = (
                (
                    "signed_evidence.finalization_digest",
                    finalization.execution_evidence_digest,
                    evidence.digest,
                    "signed execution evidence digest differs from finalization",
                ),
                (
                    "signed_evidence.session",
                    session_id,
                    evidence.session_id,
                    "signed execution evidence session differs from finalization",
                ),
                (
                    "signed_evidence.provenance",
                    finalization.provenance_digest,
                    evidence.provenance_digest,
                    "signed execution provenance differs from finalization",
                ),
                (
                    "signed_evidence.checkpoint",
                    recovery_digest,
                    evidence.checkpoint_digest,
                    "signed execution checkpoint differs from recovery checkpoint",
                ),
                (
                    "signed_evidence.session_evidence",
                    (
                        recovery.session_evidence_digest
                        if session_evidence_value is None
                        else session_evidence_value.digest
                    ),
                    evidence.session_evidence_digest,
                    "signed execution session evidence differs from durable session evidence",
                ),
                (
                    "signed_evidence.session_journal",
                    (
                        recovery.session_journal_digest
                        if not session_journal_digest
                        else session_journal_digest
                    ),
                    evidence.session_journal_digest,
                    "signed execution journal commitment differs from reconstruction",
                ),
                (
                    "signed_evidence.session_journal_manifest",
                    recovery.session_journal_manifest_digest,
                    evidence.session_journal_manifest_digest,
                    "signed execution session-journal manifest differs from recovery checkpoint",
                ),
                (
                    "signed_evidence.session_integrity",
                    (
                        recovery.session_integrity_digest
                        if not session_integrity_digest
                        else session_integrity_digest
                    ),
                    evidence.session_integrity_digest,
                    "signed execution integrity commitment differs from reconstruction",
                ),
                (
                    "signed_evidence.runtime_trust",
                    finalization.runtime_trust_digest,
                    evidence.runtime_trust_digest,
                    "signed execution runtime trust differs from finalization",
                ),
                (
                    "signed_evidence.release",
                    finalization.release_evidence_digest,
                    evidence.release_evidence_digest,
                    "signed execution release evidence differs from finalization",
                ),
                (
                    "signed_evidence.attempt",
                    finalization.execution_attempt_id,
                    evidence.execution_attempt_id,
                    "signed execution attempt differs from finalization",
                ),
                (
                    "signed_evidence.attempt_authority",
                    finalization.execution_attempt_authority_digest,
                    evidence.execution_attempt_authority_digest,
                    "signed execution attempt authority differs from finalization",
                ),
            )
            for (
                code,
                expected,
                actual,
                message,
            ) in checks:
                if expected != actual:
                    self._finding(
                        findings,
                        code,
                        RecoveryFindingSeverity.CONFLICT,
                        message,
                    )
            if (
                finalization.execution_evidence_chain_node_hash
                and finalization.execution_evidence_chain_node_hash
                != signed.chain_node_hash
            ):
                self._finding(
                    findings,
                    "signed_evidence.chain_node",
                    RecoveryFindingSeverity.CONFLICT,
                    "signed execution evidence chain node differs from finalization",
                )

        session_commit_id = ""
        session_commit_digest = ""
        session_commit_verified = False
        if self.session_commits is None:
            if self.require_session_commit:
                self._finding(
                    findings,
                    "session_commit.store_missing",
                    RecoveryFindingSeverity.MISSING,
                    "required durable session commit store is unavailable",
                )
        else:
            try:
                stored_commit = self.session_commits.get(
                    finalization_id
                )
            except DurableSessionCommitCorruption as exc:
                self._finding(
                    findings,
                    "session_commit.corruption",
                    RecoveryFindingSeverity.CORRUPTION,
                    str(exc),
                )
                stored_commit = None
            if stored_commit is None:
                if self.require_session_commit:
                    self._finding(
                        findings,
                        "session_commit.missing",
                        RecoveryFindingSeverity.MISSING,
                        "required durable session commit is missing",
                    )
            else:
                commit = stored_commit.signed.commit
                session_commit_id = commit.commit_id
                session_commit_digest = commit.digest
                commit_conflicts_before = len(findings)
                expected_pairs = (
                    (
                        "session_commit.session",
                        commit.session_id,
                        session_id,
                        "session commit session differs from finalization",
                    ),
                    (
                        "session_commit.provenance",
                        commit.provenance_digest,
                        finalization.provenance_digest,
                        "session commit provenance differs from finalization",
                    ),
                    (
                        "session_commit.finalization_semantics",
                        commit.finalization_evidence_digest,
                        finalization_evidence_digest(finalization),
                        "session commit finalization evidence binding differs",
                    ),
                    (
                        "session_commit.recovery",
                        commit.recovery_checkpoint_digest,
                        recovery_digest,
                        "session commit recovery checkpoint differs",
                    ),
                    (
                        "session_commit.session_evidence",
                        commit.session_evidence_digest,
                        (
                            ""
                            if session_evidence_value is None
                            else session_evidence_value.digest
                        ),
                        "session commit session evidence differs",
                    ),
                    (
                        "session_commit.session_journal",
                        commit.session_journal_digest,
                        session_journal_digest,
                        "session commit journal digest differs",
                    ),
                    (
                        "session_commit.session_journal_manifest",
                        commit.session_journal_manifest_digest,
                        recovery.session_journal_manifest_digest,
                        "session commit journal manifest differs from recovery",
                    ),
                    (
                        "session_commit.session_integrity",
                        commit.session_integrity_digest,
                        session_integrity_digest,
                        "session commit integrity digest differs",
                    ),
                    (
                        "session_commit.journal_root",
                        commit.journal_root,
                        journal_root,
                        "session commit journal root differs",
                    ),
                    (
                        "session_commit.receipt_root",
                        commit.receipt_root,
                        receipt_root,
                        "session commit receipt root differs",
                    ),
                    (
                        "session_commit.audit_anchor",
                        commit.audit_anchor_digest,
                        finalization.audit_anchor_digest,
                        "session commit audit anchor differs",
                    ),
                    (
                        "session_commit.audit_chain_node",
                        commit.audit_chain_node_hash,
                        finalization.audit_chain_node_hash,
                        "session commit audit chain node differs",
                    ),
                    (
                        "session_commit.audit_root",
                        commit.audit_root,
                        finalization.audit_root,
                        "session commit audit root differs",
                    ),
                    (
                        "session_commit.audit_witness",
                        commit.audit_witness_digest,
                        finalization.audit_witness_digest,
                        "session commit audit witness differs",
                    ),
                    (
                        "session_commit.audit_witness_sequence",
                        commit.audit_witness_sequence,
                        finalization.audit_witness_sequence,
                        "session commit audit witness sequence differs",
                    ),
                    (
                        "session_commit.execution_evidence",
                        commit.execution_evidence_digest,
                        signed_digest,
                        "session commit signed execution evidence differs",
                    ),
                    (
                        "session_commit.execution_chain_node",
                        commit.execution_evidence_chain_node_hash,
                        finalization.execution_evidence_chain_node_hash,
                        "session commit execution evidence chain node differs",
                    ),
                    (
                        "session_commit.runtime_trust",
                        commit.runtime_trust_digest,
                        finalization.runtime_trust_digest,
                        "session commit runtime trust differs",
                    ),
                    (
                        "session_commit.release",
                        commit.release_evidence_digest,
                        finalization.release_evidence_digest,
                        "session commit release evidence differs",
                    ),
                    (
                        "session_commit.attempt",
                        commit.execution_attempt_id,
                        finalization.execution_attempt_id,
                        "session commit execution attempt differs",
                    ),
                )
                for code, expected, actual, message in expected_pairs:
                    if expected != actual:
                        self._finding(
                            findings,
                            code,
                            RecoveryFindingSeverity.CONFLICT,
                            message,
                        )

                revision_checks = (
                    (
                        "session_commit.recovery_revision_regressed",
                        stored_recovery.revision,
                        commit.recovery_revision,
                        "recovery checkpoint revision is older than signed session commit",
                    ),
                    (
                        "session_commit.session_evidence_revision_regressed",
                        session_evidence_revision,
                        commit.session_evidence_revision,
                        "session evidence revision is older than signed session commit",
                    ),
                )
                for code, current_revision, committed_revision, message in revision_checks:
                    if (
                        committed_revision is not None
                        and (
                            current_revision is None
                            or current_revision < committed_revision
                        )
                    ):
                        self._finding(
                            findings,
                            code,
                            RecoveryFindingSeverity.CORRUPTION,
                            message,
                        )

                if commit.session_journal_revision is not None:
                    if self.session_journals is None:
                        self._finding(
                            findings,
                            "session_commit.session_journal_store_missing",
                            RecoveryFindingSeverity.MISSING,
                            "session commit binds journal manifest revision but store is unavailable",
                        )
                    else:
                        current_journal = self.session_journals.get(
                            finalization_id
                        )
                        if (
                            current_journal is None
                            or current_journal.revision
                            < commit.session_journal_revision
                        ):
                            self._finding(
                                findings,
                                "session_commit.session_journal_revision_regressed",
                                RecoveryFindingSeverity.CORRUPTION,
                                "durable session-journal revision is older than signed session commit",
                            )
                        elif (
                            current_journal.manifest.digest
                            != commit.session_journal_manifest_digest
                        ):
                            self._finding(
                                findings,
                                "session_commit.session_journal_manifest_conflict",
                                RecoveryFindingSeverity.CONFLICT,
                                "durable session-journal manifest differs from signed session commit",
                            )

                try:
                    self.session_commits.require(
                        finalization_id,
                        commit_digest=commit.digest,
                    )
                except Exception as exc:
                    self._finding(
                        findings,
                        "session_commit.publication_corruption",
                        RecoveryFindingSeverity.CORRUPTION,
                        "durable session commit publication is invalid: "
                        f"{type(exc).__name__}",
                    )

                session_commit_verified = (
                    len(findings)
                    == commit_conflicts_before
                )

        findings_tuple = tuple(findings)
        status = self._status(
            finalization,
            findings_tuple,
        )
        return DurableSessionRecoveryReport(
            finalization_id,
            session_id,
            status,
            finalization.phase.value,
            stored_finalization.revision,
            stored_recovery.revision,
            session_evidence_revision,
            finalization_digest,
            recovery_digest,
            (
                ""
                if session_evidence_value is None
                else session_evidence_value.digest
            ),
            session_journal_digest,
            session_integrity_digest,
            signed_digest,
            journal_root,
            receipt_root,
            integrity_report,
            findings_tuple,
            session_commit_id,
            session_commit_digest,
            session_commit_verified,
        )

    def require_verified(
        self,
        finalization_id: str,
    ) -> DurableSessionRecoveryReport:
        report = self.verify(
            finalization_id
        )
        if not report.ok:
            if report.findings:
                detail = (
                    report.findings[0].message
                )
            else:
                detail = (
                    "durable session recovery "
                    f"is {report.status.value}"
                )
            raise DurableRecoveryVerificationError(
                detail
            )
        return report
