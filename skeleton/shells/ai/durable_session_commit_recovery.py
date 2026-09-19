"""Crash recovery for the signed durable session commit point.

This coordinator repairs only the final cross-store commit publication.  It
never executes commands and never invents evidence.  Before publishing a
missing commit it requires the existing durable recovery verifier and
finalization reconciler to agree that all constituent evidence is complete and
consistent.

A commit record with a missing session head is also repairable because the head
is only an index over an already-signed immutable commit.  Conflicting or
corrupt records fail closed for manual review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.durable_session_commit import (
    DurableSessionCommit,
    DurableSessionCommitBuilder,
    DurableSessionCommitConflict,
    DurableSessionCommitCorruption,
    DurableSessionCommitPublication,
    DurableSessionCommitStore,
)
from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalStore,
)
from skeleton.shells.ai.finalization_reconciler import (
    AIExecutionFinalizationReconciler,
    FinalizationReconcileAction,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalizationStore,
    FinalizationPhase,
)
from skeleton.shells.ai.recovery_store import (
    AIRecoveryCheckpointStore,
)
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceStore,
)


class DurableSessionCommitRecoveryState(str, Enum):
    VERIFIED = "verified"
    COMMIT_MISSING = "commit_missing"
    HEAD_MISSING = "head_missing"
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    CORRUPT = "corrupt"


@dataclass(frozen=True)
class DurableSessionCommitRecoveryReport:
    finalization_id: str
    session_id: str
    state: DurableSessionCommitRecoveryState
    expected_commit_id: str
    expected_commit_digest: str
    existing_commit_id: str
    existing_commit_digest: str
    recovery_report_digest: str
    reconcile_report_digest: str
    recovery_status: str
    reconcile_action: str
    head_present: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.finalization_id or len(self.finalization_id) > 256:
            raise ValueError(
                "invalid commit recovery finalization_id"
            )
        if len(self.session_id) > 160:
            raise ValueError(
                "commit recovery session_id too long"
            )
        object.__setattr__(
            self,
            "state",
            DurableSessionCommitRecoveryState(
                self.state
            ),
        )
        for name in (
            "expected_commit_id",
            "expected_commit_digest",
            "existing_commit_id",
            "existing_commit_digest",
            "recovery_report_digest",
            "reconcile_report_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be digest-shaped"
                )
        if len(self.recovery_status) > 64:
            raise ValueError(
                "recovery_status too long"
            )
        if len(self.reconcile_action) > 64:
            raise ValueError(
                "reconcile_action too long"
            )
        if not isinstance(self.head_present, bool):
            raise ValueError(
                "head_present must be bool"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )
        if any(
            not reason
            or len(reason) > 2048
            for reason in self.reasons
        ):
            raise ValueError(
                "invalid commit recovery reason"
            )

    @property
    def verified(self) -> bool:
        return (
            self.state
            is DurableSessionCommitRecoveryState.VERIFIED
        )

    @property
    def repairable(self) -> bool:
        return self.state in {
            DurableSessionCommitRecoveryState.COMMIT_MISSING,
            DurableSessionCommitRecoveryState.HEAD_MISSING,
        }

    @property
    def requires_manual_review(self) -> bool:
        return self.state in {
            DurableSessionCommitRecoveryState.CONFLICT,
            DurableSessionCommitRecoveryState.CORRUPT,
        }

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
            "state": self.state.value,
            "verified": self.verified,
            "repairable": self.repairable,
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "expected_commit_id": (
                self.expected_commit_id
            ),
            "expected_commit_digest": (
                self.expected_commit_digest
            ),
            "existing_commit_id": (
                self.existing_commit_id
            ),
            "existing_commit_digest": (
                self.existing_commit_digest
            ),
            "recovery_report_digest": (
                self.recovery_report_digest
            ),
            "reconcile_report_digest": (
                self.reconcile_report_digest
            ),
            "recovery_status": self.recovery_status,
            "reconcile_action": self.reconcile_action,
            "head_present": self.head_present,
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableSessionCommitRecoveryError(RuntimeError):
    pass


class DurableSessionCommitRecoveryCoordinator:
    """Inspect and repair the final session-commit publication step."""

    def __init__(
        self,
        *,
        finalizations: AIExecutionFinalizationStore,
        recovery_checkpoints: AIRecoveryCheckpointStore,
        session_evidence: SessionEvidenceStore,
        session_journals: DurableSessionJournalStore,
        session_commits: DurableSessionCommitStore,
        recovery_verifier: DurableSessionRecoveryVerifier,
        finalization_reconciler: AIExecutionFinalizationReconciler,
        builder: DurableSessionCommitBuilder | None = None,
    ) -> None:
        expected_types = (
            (
                "finalizations",
                finalizations,
                AIExecutionFinalizationStore,
            ),
            (
                "recovery_checkpoints",
                recovery_checkpoints,
                AIRecoveryCheckpointStore,
            ),
            (
                "session_evidence",
                session_evidence,
                SessionEvidenceStore,
            ),
            (
                "session_journals",
                session_journals,
                DurableSessionJournalStore,
            ),
            (
                "session_commits",
                session_commits,
                DurableSessionCommitStore,
            ),
            (
                "recovery_verifier",
                recovery_verifier,
                DurableSessionRecoveryVerifier,
            ),
            (
                "finalization_reconciler",
                finalization_reconciler,
                AIExecutionFinalizationReconciler,
            ),
        )
        for name, value, expected in expected_types:
            if not isinstance(value, expected):
                raise TypeError(
                    f"{name} must be {expected.__name__}"
                )
        if (
            builder is not None
            and not isinstance(
                builder,
                DurableSessionCommitBuilder,
            )
        ):
            raise TypeError(
                "builder must be DurableSessionCommitBuilder"
            )
        self.finalizations = finalizations
        self.recovery_checkpoints = (
            recovery_checkpoints
        )
        self.session_evidence = session_evidence
        self.session_journals = session_journals
        self.session_commits = session_commits
        self.recovery_verifier = recovery_verifier
        self.finalization_reconciler = (
            finalization_reconciler
        )
        self.builder = (
            builder
            or DurableSessionCommitBuilder()
        )

    @staticmethod
    def _empty_report(
        finalization_id: str,
        *,
        state: DurableSessionCommitRecoveryState,
        reason: str,
        recovery_status: str = "",
        reconcile_action: str = "",
        recovery_report_digest: str = "",
        reconcile_report_digest: str = "",
        session_id: str = "",
    ) -> DurableSessionCommitRecoveryReport:
        return DurableSessionCommitRecoveryReport(
            finalization_id,
            session_id,
            state,
            "",
            "",
            "",
            "",
            recovery_report_digest,
            reconcile_report_digest,
            recovery_status,
            reconcile_action,
            False,
            (reason,),
        )

    def _expected_commit(
        self,
        finalization_id: str,
    ) -> tuple[
        DurableSessionCommit | None,
        DurableSessionCommitRecoveryReport | None,
    ]:
        stored_finalization = self.finalizations.current(
            finalization_id
        )
        if stored_finalization is None:
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.BLOCKED
                    ),
                    reason="finalization record is missing",
                ),
            )
        finalization = (
            stored_finalization.finalization
        )
        session_id = finalization.session_id
        if (
            finalization.phase
            is not FinalizationPhase.COMPLETE
        ):
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.BLOCKED
                    ),
                    reason=(
                        "finalization is not complete: "
                        f"{finalization.phase.value}"
                    ),
                    session_id=session_id,
                ),
            )

        recovery_report = (
            self.recovery_verifier.verify(
                finalization_id
            )
        )
        reconcile_report = (
            self.finalization_reconciler.inspect(
                finalization_id
            )
        )
        recovery_digest = (
            recovery_report.digest
        )
        reconcile_digest = (
            hashlib.sha256(
                json.dumps(
                    reconcile_report.to_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )

        if (
            recovery_report.status
            is DurableRecoveryStatus.MANUAL_REVIEW
        ):
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.CONFLICT
                    ),
                    reason=(
                        "durable recovery evidence requires manual review"
                    ),
                    recovery_status=(
                        recovery_report.status.value
                    ),
                    reconcile_action=(
                        reconcile_report.action.value
                    ),
                    recovery_report_digest=(
                        recovery_digest
                    ),
                    reconcile_report_digest=(
                        reconcile_digest
                    ),
                    session_id=session_id,
                ),
            )
        if not recovery_report.ok:
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.BLOCKED
                    ),
                    reason=(
                        "durable recovery evidence is incomplete"
                    ),
                    recovery_status=(
                        recovery_report.status.value
                    ),
                    reconcile_action=(
                        reconcile_report.action.value
                    ),
                    recovery_report_digest=(
                        recovery_digest
                    ),
                    reconcile_report_digest=(
                        reconcile_digest
                    ),
                    session_id=session_id,
                ),
            )
        if (
            reconcile_report.action
            is FinalizationReconcileAction.MANUAL_REVIEW
        ):
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.CONFLICT
                    ),
                    reason=(
                        "finalization evidence requires manual review"
                    ),
                    recovery_status=(
                        recovery_report.status.value
                    ),
                    reconcile_action=(
                        reconcile_report.action.value
                    ),
                    recovery_report_digest=(
                        recovery_digest
                    ),
                    reconcile_report_digest=(
                        reconcile_digest
                    ),
                    session_id=session_id,
                ),
            )
        if not reconcile_report.ok:
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.BLOCKED
                    ),
                    reason=(
                        "finalization reconciliation is incomplete"
                    ),
                    recovery_status=(
                        recovery_report.status.value
                    ),
                    reconcile_action=(
                        reconcile_report.action.value
                    ),
                    recovery_report_digest=(
                        recovery_digest
                    ),
                    reconcile_report_digest=(
                        reconcile_digest
                    ),
                    session_id=session_id,
                ),
            )

        stored_recovery = self.recovery_checkpoints.get(
            finalization_id
        )
        stored_session = self.session_evidence.current(
            session_id
        )
        stored_journal = self.session_journals.get(
            finalization_id
        )
        if (
            stored_recovery is None
            or stored_session is None
            or stored_journal is None
        ):
            missing = []
            if stored_recovery is None:
                missing.append("recovery checkpoint")
            if stored_session is None:
                missing.append("session evidence")
            if stored_journal is None:
                missing.append("session journal manifest")
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.BLOCKED
                    ),
                    reason=(
                        "required durable input is missing: "
                        + ", ".join(missing)
                    ),
                    recovery_status=(
                        recovery_report.status.value
                    ),
                    reconcile_action=(
                        reconcile_report.action.value
                    ),
                    recovery_report_digest=(
                        recovery_digest
                    ),
                    reconcile_report_digest=(
                        reconcile_digest
                    ),
                    session_id=session_id,
                ),
            )

        recovery = (
            stored_recovery.record.checkpoint
        )
        journal_manifest = (
            stored_journal.manifest
        )
        try:
            commit = self.builder.build(
                finalization=finalization,
                finalization_revision=(
                    stored_finalization.revision
                ),
                recovery_checkpoint_digest=(
                    recovery.digest
                ),
                recovery_revision=(
                    stored_recovery.revision
                ),
                session_evidence_digest=(
                    stored_session.evidence.digest
                ),
                session_evidence_revision=(
                    stored_session.revision
                ),
                session_journal_digest=(
                    recovery_report.session_journal_digest
                ),
                session_journal_manifest_digest=(
                    journal_manifest.digest
                ),
                session_journal_revision=(
                    stored_journal.revision
                ),
                session_integrity_digest=(
                    recovery_report.session_integrity_digest
                ),
                journal_root=(
                    recovery_report.journal_root
                ),
                receipt_root=(
                    recovery_report.receipt_root
                ),
                audit_anchor_digest=(
                    finalization.audit_anchor_digest
                ),
                audit_chain_node_hash=(
                    finalization.audit_chain_node_hash
                ),
                audit_root=(
                    finalization.audit_root
                ),
                audit_witness_digest=(
                    finalization.audit_witness_digest
                ),
                audit_witness_sequence=(
                    finalization.audit_witness_sequence
                ),
                execution_evidence_digest=(
                    finalization.execution_evidence_digest
                ),
                execution_evidence_chain_node_hash=(
                    finalization.execution_evidence_chain_node_hash
                ),
            )
        except Exception as exc:
            return (
                None,
                self._empty_report(
                    finalization_id,
                    state=(
                        DurableSessionCommitRecoveryState.CONFLICT
                    ),
                    reason=(
                        "unable to reconstruct deterministic session commit: "
                        f"{type(exc).__name__}"
                    ),
                    recovery_status=(
                        recovery_report.status.value
                    ),
                    reconcile_action=(
                        reconcile_report.action.value
                    ),
                    recovery_report_digest=(
                        recovery_digest
                    ),
                    reconcile_report_digest=(
                        reconcile_digest
                    ),
                    session_id=session_id,
                ),
            )
        return commit, None

    def inspect(
        self,
        finalization_id: str,
    ) -> DurableSessionCommitRecoveryReport:
        if not finalization_id or len(finalization_id) > 256:
            raise ValueError(
                "invalid finalization_id"
            )

        expected, blocked = self._expected_commit(
            finalization_id
        )
        if blocked is not None:
            return blocked
        assert expected is not None

        recovery_report = (
            self.recovery_verifier.verify(
                finalization_id
            )
        )
        reconcile_report = (
            self.finalization_reconciler.inspect(
                finalization_id
            )
        )
        reconcile_digest = hashlib.sha256(
            json.dumps(
                reconcile_report.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        try:
            existing = self.session_commits.get(
                finalization_id
            )
        except DurableSessionCommitCorruption as exc:
            return DurableSessionCommitRecoveryReport(
                finalization_id,
                expected.session_id,
                DurableSessionCommitRecoveryState.CORRUPT,
                expected.commit_id,
                expected.digest,
                "",
                "",
                recovery_report.digest,
                reconcile_digest,
                recovery_report.status.value,
                reconcile_report.action.value,
                False,
                (str(exc),),
            )

        if existing is None:
            return DurableSessionCommitRecoveryReport(
                finalization_id,
                expected.session_id,
                DurableSessionCommitRecoveryState.COMMIT_MISSING,
                expected.commit_id,
                expected.digest,
                "",
                "",
                recovery_report.digest,
                reconcile_digest,
                recovery_report.status.value,
                reconcile_report.action.value,
                False,
                (
                    "all durable evidence is verified but session commit is missing",
                ),
            )

        actual = existing.signed.commit
        if actual.digest != expected.digest:
            return DurableSessionCommitRecoveryReport(
                finalization_id,
                expected.session_id,
                DurableSessionCommitRecoveryState.CONFLICT,
                expected.commit_id,
                expected.digest,
                actual.commit_id,
                actual.digest,
                recovery_report.digest,
                reconcile_digest,
                recovery_report.status.value,
                reconcile_report.action.value,
                bool(
                    self.session_commits.head(
                        expected.session_id
                    )
                ),
                (
                    "existing session commit differs from deterministic reconstruction",
                ),
            )

        head = self.session_commits.head(
            expected.session_id
        )
        if head is None:
            return DurableSessionCommitRecoveryReport(
                finalization_id,
                expected.session_id,
                DurableSessionCommitRecoveryState.HEAD_MISSING,
                expected.commit_id,
                expected.digest,
                actual.commit_id,
                actual.digest,
                recovery_report.digest,
                reconcile_digest,
                recovery_report.status.value,
                reconcile_report.action.value,
                False,
                (
                    "signed session commit exists but session head is missing",
                ),
            )
        try:
            required = self.session_commits.require(
                finalization_id,
                commit_digest=expected.digest,
            )
        except (
            DurableSessionCommitConflict,
            DurableSessionCommitCorruption,
        ) as exc:
            return DurableSessionCommitRecoveryReport(
                finalization_id,
                expected.session_id,
                DurableSessionCommitRecoveryState.CORRUPT,
                expected.commit_id,
                expected.digest,
                actual.commit_id,
                actual.digest,
                recovery_report.digest,
                reconcile_digest,
                recovery_report.status.value,
                reconcile_report.action.value,
                True,
                (str(exc),),
            )
        if required.signed.commit.digest != expected.digest:
            return DurableSessionCommitRecoveryReport(
                finalization_id,
                expected.session_id,
                DurableSessionCommitRecoveryState.CONFLICT,
                expected.commit_id,
                expected.digest,
                required.signed.commit.commit_id,
                required.signed.commit.digest,
                recovery_report.digest,
                reconcile_digest,
                recovery_report.status.value,
                reconcile_report.action.value,
                True,
                (
                    "required session commit differs from reconstruction",
                ),
            )
        return DurableSessionCommitRecoveryReport(
            finalization_id,
            expected.session_id,
            DurableSessionCommitRecoveryState.VERIFIED,
            expected.commit_id,
            expected.digest,
            actual.commit_id,
            actual.digest,
            recovery_report.digest,
            reconcile_digest,
            recovery_report.status.value,
            reconcile_report.action.value,
            True,
            (),
        )

    def repair(
        self,
        finalization_id: str,
    ) -> DurableSessionCommitPublication:
        report = self.inspect(
            finalization_id
        )
        if report.verified:
            stored = self.session_commits.require(
                finalization_id,
                commit_digest=(
                    report.expected_commit_digest
                ),
            )
            head_revision, head = (
                self.session_commits.head(
                    stored.signed.commit.session_id
                )
            )
            return DurableSessionCommitPublication(
                stored,
                head_revision,
                head,
                False,
            )
        if not report.repairable:
            raise DurableSessionCommitRecoveryError(
                report.reasons[0]
                if report.reasons
                else (
                    "session commit is not safely repairable"
                )
            )

        expected, blocked = self._expected_commit(
            finalization_id
        )
        if blocked is not None or expected is None:
            raise DurableSessionCommitRecoveryError(
                (
                    blocked.reasons[0]
                    if blocked is not None
                    and blocked.reasons
                    else "session commit reconstruction failed"
                )
            )
        publication = self.session_commits.publish(
            expected
        )
        after = self.inspect(
            finalization_id
        )
        if not after.verified:
            raise DurableSessionCommitRecoveryError(
                "session commit repair did not reach verified state"
            )
        return publication
