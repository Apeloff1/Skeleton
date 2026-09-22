"""High-assurance recovery using durable journal and session-scoped evidence."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptRecovery,
)
from skeleton.shells.ai.recovery import (
    AIRecoveryManager,
    AIRecoveryReport,
    RecoveryAction,
)
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.session_evidence import SessionEvidenceStore
from skeleton.shells.ai.session_journal import SessionJournalEvidence


@dataclass(frozen=True)
class StrictRecoveryReport:
    action: RecoveryAction
    reasons: tuple[str, ...]
    base: AIRecoveryReport
    journal_root_matches: bool
    session_journal_matches: bool
    global_receipt_chain_valid: bool
    session_evidence_matches: bool
    release_evidence_matches: bool
    sandbox_binding_matches: bool
    runtime_trust_matches: bool
    authority_health_policy_matches: bool
    execution_attempt_matches: bool
    execution_attempt_recovery: str

    @property
    def safe_to_resume(self) -> bool:
        return self.action in {
            RecoveryAction.NONE,
            RecoveryAction.RESUME_REVIEW,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "reasons": list(self.reasons),
            "safe_to_resume": self.safe_to_resume,
            "base": self.base.to_dict(),
            "journal_root_matches": self.journal_root_matches,
            "session_journal_matches": self.session_journal_matches,
            "global_receipt_chain_valid": self.global_receipt_chain_valid,
            "session_evidence_matches": self.session_evidence_matches,
            "release_evidence_matches": self.release_evidence_matches,
            "sandbox_binding_matches": self.sandbox_binding_matches,
            "runtime_trust_matches": self.runtime_trust_matches,
            "authority_health_policy_matches": (
                self.authority_health_policy_matches
            ),
            "execution_attempt_matches": self.execution_attempt_matches,
            "execution_attempt_recovery": self.execution_attempt_recovery,
        }


class StrictAIRecoveryManager:
    """Combine checkpoint, durable session evidence, and attempt evidence.

    Recovery obligations are monotonic: later checks may strengthen an action,
    never weaken an integrity or side-effect concern raised by an earlier
    layer.
    """

    _PRIORITY = {
        RecoveryAction.NONE: 0,
        RecoveryAction.RESUME_REVIEW: 10,
        RecoveryAction.REQUIRE_REPLAN: 30,
        RecoveryAction.MARK_FAILED: 40,
        RecoveryAction.REQUIRE_VERIFICATION: 50,
        RecoveryAction.MANUAL_REVIEW: 60,
    }

    def __init__(
        self,
        *,
        base: AIRecoveryManager | None = None,
    ) -> None:
        self.base = base or AIRecoveryManager()

    @classmethod
    def _stronger(
        cls,
        current: RecoveryAction,
        candidate: RecoveryAction,
    ) -> RecoveryAction:
        return (
            candidate
            if cls._PRIORITY[candidate] > cls._PRIORITY[current]
            else current
        )

    def inspect(
        self,
        checkpoint: AIRecoveryCheckpoint,
        journal,
        receipt_chain,
        session_evidence: SessionEvidenceStore,
        *,
        current_policy_fingerprint: str,
        current_tool_catalog_digest: str,
        current_effect_digest: str,
        current_release_evidence_digest: str = "",
        current_sandbox_binding_digest: str = "",
        current_runtime_trust_digest: str = "",
        current_authority_health_policy_digest: str = "",
        execution_attempts: AIExecutionAttemptStore | None = None,
    ) -> StrictRecoveryReport:
        session = checkpoint.session

        journal_valid = journal.verify()
        journal_root_matches = journal.root_hash() == session.journal_root
        current_session_journal = SessionJournalEvidence.from_journal(
            journal,
            session.session_id,
        )
        if checkpoint.session_journal_digest:
            session_journal_matches = (
                current_session_journal.digest
                == checkpoint.session_journal_digest
            )
        else:
            session_journal_matches = journal_root_matches

        receipt_valid = receipt_chain.verify()
        stored = session_evidence.current(session.session_id)
        if checkpoint.session_evidence_digest:
            session_evidence_matches = (
                stored is not None
                and stored.evidence.digest
                == checkpoint.session_evidence_digest
            )
        else:
            session_evidence_matches = stored is None

        release_matches = (
            not checkpoint.release_evidence_digest
            or checkpoint.release_evidence_digest
            == current_release_evidence_digest
        )
        sandbox_matches = (
            not checkpoint.sandbox_binding_digest
            or checkpoint.sandbox_binding_digest
            == current_sandbox_binding_digest
        )
        runtime_trust_matches = (
            not checkpoint.runtime_trust_digest
            or checkpoint.runtime_trust_digest
            == current_runtime_trust_digest
        )
        authority_health_policy_matches = (
            not checkpoint.authority_health_policy_digest
            or checkpoint.authority_health_policy_digest
            == current_authority_health_policy_digest
        )

        execution_attempt_matches = True
        execution_attempt_recovery = ""
        attempt = None
        if checkpoint.execution_attempt_id:
            if execution_attempts is None:
                execution_attempt_matches = False
            else:
                stored_attempt = execution_attempts.current(
                    checkpoint.execution_attempt_id
                )
                if stored_attempt is None:
                    execution_attempt_matches = False
                else:
                    attempt = stored_attempt.attempt
                    execution_attempt_matches = (
                        attempt.authority_digest
                        == checkpoint.execution_attempt_authority_digest
                    )
                    execution_attempt_recovery = attempt.recovery.value

        # Global receipt chains may legitimately advance because another AI
        # session executed. Session-scoped evidence below is authoritative for
        # this checkpoint, so the legacy base manager receives the checkpoint's
        # own receipt root instead of the current global head.
        base = self.base.inspect(
            session,
            journal,
            current_receipt_root=session.receipt_root,
            current_policy_fingerprint=current_policy_fingerprint,
            current_tool_catalog_digest=current_tool_catalog_digest,
            current_effect_digest=current_effect_digest,
        )
        reasons = list(base.reasons)
        action = base.action

        if not journal_valid:
            action = self._stronger(
                action,
                RecoveryAction.MANUAL_REVIEW,
            )
            if "AI decision journal integrity failure" not in reasons:
                reasons.append("AI decision journal integrity failure")
        elif not session_journal_matches:
            action = self._stronger(
                action,
                RecoveryAction.MANUAL_REVIEW,
            )
            reasons.append(
                "AI session journal commitment differs from checkpoint"
            )

        if not receipt_valid:
            action = self._stronger(
                action,
                RecoveryAction.MANUAL_REVIEW,
            )
            reasons.append(
                "global shell receipt chain integrity failure"
            )

        if not release_matches:
            action = self._stronger(
                action,
                RecoveryAction.REQUIRE_REPLAN,
            )
            reasons.append("release evidence changed since checkpoint")
        if not sandbox_matches:
            action = self._stronger(
                action,
                RecoveryAction.REQUIRE_REPLAN,
            )
            reasons.append("sandbox binding changed since checkpoint")
        if not runtime_trust_matches:
            action = self._stronger(
                action,
                RecoveryAction.REQUIRE_REPLAN,
            )
            reasons.append(
                "runtime trust epoch changed since checkpoint"
            )
        if not authority_health_policy_matches:
            action = self._stronger(
                action,
                RecoveryAction.REQUIRE_REPLAN,
            )
            reasons.append(
                "authority health policy changed since checkpoint"
            )

        if checkpoint.execution_attempt_id:
            if not execution_attempt_matches:
                action = self._stronger(
                    action,
                    RecoveryAction.MANUAL_REVIEW,
                )
                reasons.append(
                    "execution attempt evidence is missing or differs "
                    "from checkpoint"
                )
            elif attempt is not None:
                if (
                    attempt.recovery
                    is ExecutionAttemptRecovery.NOT_STARTED
                ):
                    action = self._stronger(
                        action,
                        RecoveryAction.REQUIRE_REPLAN,
                    )
                    reasons.append(
                        "execution seal was consumed but process boundary "
                        "was not entered"
                    )
                elif (
                    attempt.recovery
                    is ExecutionAttemptRecovery.REQUIRE_VERIFICATION
                ):
                    action = self._stronger(
                        action,
                        RecoveryAction.REQUIRE_VERIFICATION,
                    )
                    reasons.append(
                        "execution attempt crossed process boundary "
                        "without terminal evidence"
                    )
                elif (
                    attempt.recovery
                    is ExecutionAttemptRecovery.TERMINAL_FAILURE
                ):
                    if attempt.terminal_evidence_digest:
                        action = self._stronger(
                            action,
                            RecoveryAction.MARK_FAILED,
                        )
                        reasons.append(
                            "execution attempt recorded terminal failure "
                            "with terminal evidence"
                        )
                    else:
                        action = self._stronger(
                            action,
                            RecoveryAction.REQUIRE_VERIFICATION,
                        )
                        reasons.append(
                            "execution attempt failed after process "
                            "boundary without terminal evidence"
                        )
                elif (
                    attempt.recovery
                    is ExecutionAttemptRecovery.TERMINAL_SUCCESS
                ):
                    if not attempt.terminal_evidence_digest:
                        action = self._stronger(
                            action,
                            RecoveryAction.MANUAL_REVIEW,
                        )
                        reasons.append(
                            "successful execution attempt lacks terminal "
                            "evidence digest"
                        )
                    elif session.phase != "complete":
                        action = self._stronger(
                            action,
                            RecoveryAction.REQUIRE_VERIFICATION,
                        )
                        reasons.append(
                            "successful execution attempt is newer than the "
                            "persisted session checkpoint"
                        )
                elif (
                    attempt.recovery
                    is ExecutionAttemptRecovery.ABANDONED
                ):
                    action = self._stronger(
                        action,
                        RecoveryAction.REQUIRE_REPLAN,
                    )
                    reasons.append(
                        "execution attempt was abandoned before process "
                        "boundary"
                    )

        if not session_evidence_matches:
            if session.phase in {
                "executing",
                "verifying",
                "complete",
            }:
                action = self._stronger(
                    action,
                    RecoveryAction.REQUIRE_VERIFICATION,
                )
                reasons.append(
                    "session-scoped execution evidence differs from checkpoint"
                )
            elif checkpoint.session_evidence_digest:
                action = self._stronger(
                    action,
                    RecoveryAction.MANUAL_REVIEW,
                )
                reasons.append(
                    "unexpected session execution evidence drift"
                )

        reasons = list(dict.fromkeys(reasons))
        return StrictRecoveryReport(
            action,
            tuple(reasons),
            base,
            journal_root_matches,
            session_journal_matches,
            receipt_valid,
            session_evidence_matches,
            release_matches,
            sandbox_matches,
            runtime_trust_matches,
            authority_health_policy_matches,
            execution_attempt_matches,
            execution_attempt_recovery,
        )
