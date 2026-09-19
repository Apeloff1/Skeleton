"""Recovery inspection and reconciliation for durable execution obligations.

The obligation catalog answers the restart question "which sealed executions
must this worker account for?" This module combines that discoverable set with
execution-attempt evidence, finalization state, and end-to-end durable recovery.

It never replays an execution. Boundary-entered ambiguity remains fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    AIExecutionAttemptStore,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_obligation import (
    AIExecutionObligation,
    AIExecutionObligationStore,
    ExecutionObligationConflict,
    ExecutionObligationState,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    AIExecutionFinalizationStore,
    FinalizationPhase,
)


class ExecutionObligationRecoveryDisposition(str, Enum):
    SAFE_NOT_STARTED = "safe_not_started"
    AMBIGUOUS_BOUNDARY = "ambiguous_boundary"
    TERMINAL_UNFINALIZED = "terminal_unfinalized"
    FINALIZATION_DISCOVERED = "finalization_discovered"
    VERIFIED_FINALIZED = "verified_finalized"
    RETIRED = "retired"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class ExecutionObligationRecoveryReport:
    obligation_id: str
    session_id: str
    disposition: ExecutionObligationRecoveryDisposition
    reasons: tuple[str, ...]
    obligation: AIExecutionObligation
    attempt: AIExecutionAttempt | None
    derived_finalization_id: str = ""
    finalization: AIExecutionFinalization | None = None
    durable_recovery: DurableSessionRecoveryReport | None = None

    def __post_init__(self) -> None:
        if not self.obligation_id or len(self.obligation_id) > 256:
            raise ValueError("invalid obligation recovery obligation_id")
        if not self.session_id or len(self.session_id) > 256:
            raise ValueError("invalid obligation recovery session_id")
        object.__setattr__(
            self,
            "disposition",
            ExecutionObligationRecoveryDisposition(self.disposition),
        )
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.obligation.obligation_id != self.obligation_id:
            raise ValueError("recovery report obligation identity mismatch")
        if self.obligation.session_id != self.session_id:
            raise ValueError("recovery report session identity mismatch")
        if self.attempt is not None and self.attempt.attempt_id != self.obligation_id:
            raise ValueError("recovery report attempt identity mismatch")
        if len(self.derived_finalization_id) > 256:
            raise ValueError("derived_finalization_id too long")
        if self.finalization is not None and (
            self.finalization.finalization_id != self.derived_finalization_id
        ):
            raise ValueError("recovery report finalization identity mismatch")
        if self.durable_recovery is not None and (
            self.durable_recovery.finalization_id
            != self.derived_finalization_id
        ):
            raise ValueError("durable recovery/finalization identity mismatch")

    @property
    def safe_to_replan(self) -> bool:
        return self.disposition is ExecutionObligationRecoveryDisposition.SAFE_NOT_STARTED

    @property
    def requires_manual_review(self) -> bool:
        return self.disposition in {
            ExecutionObligationRecoveryDisposition.AMBIGUOUS_BOUNDARY,
            ExecutionObligationRecoveryDisposition.TERMINAL_UNFINALIZED,
            ExecutionObligationRecoveryDisposition.MANUAL_REVIEW,
        }

    @property
    def verified(self) -> bool:
        return self.disposition is ExecutionObligationRecoveryDisposition.VERIFIED_FINALIZED

    @property
    def terminal(self) -> bool:
        return self.disposition in {
            ExecutionObligationRecoveryDisposition.VERIFIED_FINALIZED,
            ExecutionObligationRecoveryDisposition.RETIRED,
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
            "obligation_id": self.obligation_id,
            "session_id": self.session_id,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "safe_to_replan": self.safe_to_replan,
            "requires_manual_review": self.requires_manual_review,
            "verified": self.verified,
            "terminal": self.terminal,
            "obligation": self.obligation.to_dict(),
            "attempt": (
                None if self.attempt is None else self.attempt.to_dict()
            ),
            "derived_finalization_id": self.derived_finalization_id,
            "finalization": (
                None
                if self.finalization is None
                else self.finalization.to_dict()
            ),
            "durable_recovery": (
                None
                if self.durable_recovery is None
                else self.durable_recovery.to_dict()
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class ExecutionObligationRecoveryError(RuntimeError):
    pass


class AIExecutionObligationRecoveryInspector:
    """Classify and reconcile all discoverable execution obligations."""

    def __init__(
        self,
        obligations: AIExecutionObligationStore,
        attempts: AIExecutionAttemptStore,
        finalizations: AIExecutionFinalizationStore,
        durable_recovery: DurableSessionRecoveryVerifier,
        *,
        max_scan: int = 100_000,
    ) -> None:
        if not isinstance(obligations, AIExecutionObligationStore):
            raise TypeError("obligations must be AIExecutionObligationStore")
        if not isinstance(attempts, AIExecutionAttemptStore):
            raise TypeError("attempts must be AIExecutionAttemptStore")
        if not isinstance(finalizations, AIExecutionFinalizationStore):
            raise TypeError("finalizations must be AIExecutionFinalizationStore")
        if not isinstance(durable_recovery, DurableSessionRecoveryVerifier):
            raise TypeError("durable_recovery must be DurableSessionRecoveryVerifier")
        if (
            isinstance(max_scan, bool)
            or not isinstance(max_scan, int)
            or max_scan <= 0
        ):
            raise ValueError("max_scan must be positive")
        self.obligations = obligations
        self.attempts = attempts
        self.finalizations = finalizations
        self.durable_recovery = durable_recovery
        self.max_scan = max_scan

    @staticmethod
    def _authority_mismatches(
        obligation: AIExecutionObligation,
        attempt: AIExecutionAttempt,
    ) -> tuple[str, ...]:
        mismatches: list[str] = []
        checks = (
            ("session_id", "session"),
            ("principal", "principal"),
            ("plan_fingerprint", "plan"),
            ("execution_seal_id", "execution seal"),
        )
        for field, label in checks:
            if getattr(obligation, field) != getattr(attempt, field):
                mismatches.append(f"execution obligation {label} mismatch")
        if obligation.obligation_id != attempt.attempt_id:
            mismatches.append("execution obligation attempt id mismatch")
        if (
            obligation.runtime_trust_digest
            and obligation.runtime_trust_digest != attempt.runtime_trust_digest
        ):
            mismatches.append("execution obligation runtime trust mismatch")
        if (
            obligation.release_evidence_digest
            and obligation.release_evidence_digest
            != attempt.release_evidence_digest
        ):
            mismatches.append("execution obligation release evidence mismatch")
        if (
            obligation.attempt_authority_digest
            and obligation.attempt_authority_digest != attempt.authority_digest
        ):
            mismatches.append("execution obligation attempt authority mismatch")
        return tuple(mismatches)

    @staticmethod
    def _derive_finalization_id(
        obligation: AIExecutionObligation,
        attempt: AIExecutionAttempt,
    ) -> str:
        if not attempt.terminal_evidence_digest:
            return ""
        return AIExecutionFinalization.derive_id(
            session_id=obligation.session_id,
            provenance_digest=attempt.terminal_evidence_digest,
            execution_attempt_id=attempt.attempt_id,
        )

    def inspect(
        self,
        obligation_id: str,
    ) -> ExecutionObligationRecoveryReport:
        stored = self.obligations.current(obligation_id)
        if stored is None:
            raise ExecutionObligationRecoveryError(
                "execution obligation is missing"
            )
        obligation = stored.obligation

        if obligation.state is ExecutionObligationState.RETIRED:
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.RETIRED,
                ("execution obligation was explicitly retired",),
                obligation,
                None,
            )

        attempt_record = self.attempts.current(obligation_id)
        attempt = None if attempt_record is None else attempt_record.attempt
        if attempt is None:
            if obligation.state is ExecutionObligationState.REGISTERED:
                return ExecutionObligationRecoveryReport(
                    obligation.obligation_id,
                    obligation.session_id,
                    ExecutionObligationRecoveryDisposition.SAFE_NOT_STARTED,
                    (
                        "execution obligation was cataloged but no attempt "
                        "authority was reserved",
                    ),
                    obligation,
                    None,
                )
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.MANUAL_REVIEW,
                ("execution obligation references missing attempt evidence",),
                obligation,
                None,
            )

        mismatches = self._authority_mismatches(obligation, attempt)
        if mismatches:
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.MANUAL_REVIEW,
                mismatches,
                obligation,
                attempt,
            )

        if attempt.state in {
            ExecutionAttemptState.AUTHORIZED,
            ExecutionAttemptState.ABANDONED,
        }:
            if obligation.state is ExecutionObligationState.FINALIZED:
                return ExecutionObligationRecoveryReport(
                    obligation.obligation_id,
                    obligation.session_id,
                    ExecutionObligationRecoveryDisposition.MANUAL_REVIEW,
                    ("finalized obligation points to non-executed attempt",),
                    obligation,
                    attempt,
                )
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.SAFE_NOT_STARTED,
                (
                    "execution attempt never entered process boundary"
                    if attempt.state is ExecutionAttemptState.AUTHORIZED
                    else "execution attempt was abandoned before process boundary"
                ,),
                obligation,
                attempt,
            )

        if attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED:
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.AMBIGUOUS_BOUNDARY,
                (
                    "execution attempt entered process boundary without "
                    "terminal evidence; replay is forbidden",
                ),
                obligation,
                attempt,
            )

        derived = self._derive_finalization_id(obligation, attempt)
        if not derived:
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.TERMINAL_UNFINALIZED,
                ("terminal execution attempt lacks provenance evidence",),
                obligation,
                attempt,
            )

        finalization_record = self.finalizations.current(derived)
        finalization = (
            None
            if finalization_record is None
            else finalization_record.finalization
        )
        if finalization is None:
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.TERMINAL_UNFINALIZED,
                (
                    "terminal execution is discoverable but no durable "
                    "finalization exists",
                ),
                obligation,
                attempt,
                derived,
            )

        if finalization.phase is not FinalizationPhase.COMPLETE:
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                ExecutionObligationRecoveryDisposition.FINALIZATION_DISCOVERED,
                (
                    "durable finalization exists but is not complete: "
                    f"{finalization.phase.value}",
                ),
                obligation,
                attempt,
                derived,
                finalization,
            )

        recovery = self.durable_recovery.verify(derived)
        if recovery.status is DurableRecoveryStatus.VERIFIED:
            disposition = (
                ExecutionObligationRecoveryDisposition.VERIFIED_FINALIZED
                if obligation.state is ExecutionObligationState.FINALIZED
                else ExecutionObligationRecoveryDisposition.FINALIZATION_DISCOVERED
            )
            reason = (
                "execution obligation and durable finalization are verified"
                if disposition
                is ExecutionObligationRecoveryDisposition.VERIFIED_FINALIZED
                else (
                    "verified durable finalization can be linked to "
                    "execution obligation"
                )
            )
            return ExecutionObligationRecoveryReport(
                obligation.obligation_id,
                obligation.session_id,
                disposition,
                (reason,),
                obligation,
                attempt,
                derived,
                finalization,
                recovery,
            )

        return ExecutionObligationRecoveryReport(
            obligation.obligation_id,
            obligation.session_id,
            ExecutionObligationRecoveryDisposition.MANUAL_REVIEW,
            (
                "durable finalization recovery status is "
                f"{recovery.status.value}",
            ),
            obligation,
            attempt,
            derived,
            finalization,
            recovery,
        )

    def reconcile(
        self,
        obligation_id: str,
    ) -> ExecutionObligationRecoveryReport:
        report = self.inspect(obligation_id)
        obligation = report.obligation

        if report.attempt is not None and obligation.state in {
            ExecutionObligationState.REGISTERED,
            ExecutionObligationState.ATTEMPT_BOUND,
        }:
            self.obligations.sync_attempt(
                obligation_id,
                report.attempt,
            )

        if (
            report.disposition
            is ExecutionObligationRecoveryDisposition.FINALIZATION_DISCOVERED
            and report.finalization is not None
            and report.durable_recovery is not None
            and report.durable_recovery.status
            is DurableRecoveryStatus.VERIFIED
        ):
            self.obligations.finalize(
                obligation_id,
                report.finalization,
            )
        return self.inspect(obligation_id)

    def inspect_all(
        self,
    ) -> tuple[ExecutionObligationRecoveryReport, ...]:
        obligations = self.obligations.obligations()
        if len(obligations) > self.max_scan:
            raise ExecutionObligationRecoveryError(
                "execution obligation scan bound exceeded"
            )
        return tuple(
            self.inspect(item.obligation.obligation_id)
            for item in obligations
        )

    def reconcile_all(
        self,
    ) -> tuple[ExecutionObligationRecoveryReport, ...]:
        obligations = self.obligations.obligations()
        if len(obligations) > self.max_scan:
            raise ExecutionObligationRecoveryError(
                "execution obligation scan bound exceeded"
            )
        return tuple(
            self.reconcile(item.obligation.obligation_id)
            for item in obligations
        )

    def require_no_ambiguous_side_effects(
        self,
    ) -> tuple[ExecutionObligationRecoveryReport, ...]:
        reports = self.inspect_all()
        unsafe = tuple(
            item
            for item in reports
            if item.disposition
            in {
                ExecutionObligationRecoveryDisposition.AMBIGUOUS_BOUNDARY,
                ExecutionObligationRecoveryDisposition.TERMINAL_UNFINALIZED,
                ExecutionObligationRecoveryDisposition.MANUAL_REVIEW,
            }
        )
        if unsafe:
            first = unsafe[0]
            raise ExecutionObligationRecoveryError(
                f"{first.obligation_id}: {first.reasons[0]}"
            )
        return reports
