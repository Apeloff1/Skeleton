"""Checkpoint-independent recovery inspection for durable execution attempts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttempt,
    AIExecutionAttemptStore,
    ExecutionAttemptConflict,
    ExecutionAttemptRecovery,
)


class AttemptRecoveryDisposition(str, Enum):
    NO_ATTEMPT = "no_attempt"
    REPLAN = "replan"
    VERIFY = "verify"
    TERMINAL_SUCCESS = "terminal_success"
    TERMINAL_FAILURE = "terminal_failure"
    MANUAL_REVIEW = "manual_review"


def _optional_digest(name: str, value: str) -> str:
    if not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class AttemptRecoveryExpectation:
    """Optional identity constraints known by the recovery coordinator."""

    principal: str = ""
    worker_id: str = ""
    plan_fingerprint: str = ""
    execution_seal_id: str = ""
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    execution_backend_id: str = ""
    terminal_evidence_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "principal",
            "worker_id",
            "execution_seal_id",
            "execution_backend_id",
        ):
            value = getattr(self, name)
            if len(value) > 256:
                raise ValueError(f"{name} too long")
        for name in (
            "plan_fingerprint",
            "runtime_trust_digest",
            "release_evidence_digest",
            "terminal_evidence_digest",
        ):
            object.__setattr__(
                self,
                name,
                _optional_digest(name, getattr(self, name)),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "principal": self.principal,
            "worker_id": self.worker_id,
            "plan_fingerprint": self.plan_fingerprint,
            "execution_seal_id": self.execution_seal_id,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "execution_backend_id": self.execution_backend_id,
            "terminal_evidence_digest": self.terminal_evidence_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AttemptRecoveryReport:
    session_id: str
    disposition: AttemptRecoveryDisposition
    reasons: tuple[str, ...]
    attempt: AIExecutionAttempt | None
    expectation_digest: str
    authority_matches: bool

    @property
    def attempt_id(self) -> str:
        return "" if self.attempt is None else self.attempt.attempt_id

    @property
    def safe_to_replan(self) -> bool:
        return (
            self.disposition is AttemptRecoveryDisposition.REPLAN
            and self.authority_matches
        )

    @property
    def requires_verification(self) -> bool:
        return self.disposition is AttemptRecoveryDisposition.VERIFY

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "attempt": (
                None if self.attempt is None else self.attempt.to_dict()
            ),
            "attempt_id": self.attempt_id,
            "expectation_digest": self.expectation_digest,
            "authority_matches": self.authority_matches,
            "safe_to_replan": self.safe_to_replan,
            "requires_verification": self.requires_verification,
        }


class AIExecutionAttemptRecoveryInspector:
    """Classify durable attempt evidence without requiring a final checkpoint."""

    def __init__(self, store: AIExecutionAttemptStore) -> None:
        if not isinstance(store, AIExecutionAttemptStore):
            raise TypeError("store must be AIExecutionAttemptStore")
        self.store = store

    @staticmethod
    def _mismatches(
        attempt: AIExecutionAttempt,
        expected: AttemptRecoveryExpectation,
    ) -> tuple[str, ...]:
        reasons = []
        fields = (
            ("principal", "principal"),
            ("worker_id", "worker"),
            ("plan_fingerprint", "plan"),
            ("execution_seal_id", "execution seal"),
            ("runtime_trust_digest", "runtime trust"),
            ("release_evidence_digest", "release evidence"),
            ("execution_backend_id", "execution backend"),
        )
        for field, label in fields:
            expected_value = getattr(expected, field)
            if expected_value and getattr(attempt, field) != expected_value:
                reasons.append(f"execution attempt {label} mismatch")
        if (
            expected.terminal_evidence_digest
            and attempt.terminal_evidence_digest
            != expected.terminal_evidence_digest
        ):
            reasons.append("execution attempt terminal evidence mismatch")
        return tuple(reasons)

    @staticmethod
    def _classify(
        attempt: AIExecutionAttempt,
    ) -> tuple[AttemptRecoveryDisposition, tuple[str, ...]]:
        recovery = attempt.recovery
        if recovery is ExecutionAttemptRecovery.NOT_STARTED:
            return (
                AttemptRecoveryDisposition.REPLAN,
                (
                    "execution authority was consumed but process boundary "
                    "was not entered",
                ),
            )
        if recovery is ExecutionAttemptRecovery.ABANDONED:
            return (
                AttemptRecoveryDisposition.REPLAN,
                ("execution attempt was abandoned before process boundary",),
            )
        if recovery is ExecutionAttemptRecovery.REQUIRE_VERIFICATION:
            return (
                AttemptRecoveryDisposition.VERIFY,
                (
                    "execution attempt crossed process boundary without "
                    "terminal state",
                ),
            )
        if recovery is ExecutionAttemptRecovery.TERMINAL_SUCCESS:
            if not attempt.terminal_evidence_digest:
                return (
                    AttemptRecoveryDisposition.MANUAL_REVIEW,
                    ("successful attempt lacks terminal evidence",),
                )
            return (
                AttemptRecoveryDisposition.TERMINAL_SUCCESS,
                ("execution attempt recorded terminal success",),
            )
        if recovery is ExecutionAttemptRecovery.TERMINAL_FAILURE:
            if not attempt.terminal_evidence_digest:
                return (
                    AttemptRecoveryDisposition.VERIFY,
                    (
                        "failed attempt crossed process boundary without "
                        "terminal evidence",
                    ),
                )
            return (
                AttemptRecoveryDisposition.TERMINAL_FAILURE,
                ("execution attempt recorded terminal failure",),
            )
        return (
            AttemptRecoveryDisposition.MANUAL_REVIEW,
            ("unknown execution attempt recovery state",),
        )

    def inspect(
        self,
        session_id: str,
        *,
        expectation: AttemptRecoveryExpectation | None = None,
    ) -> AttemptRecoveryReport:
        if not session_id or len(session_id) > 256:
            raise ValueError("invalid recovery session_id")
        expected = expectation or AttemptRecoveryExpectation()
        try:
            stored = self.store.current_for_session(session_id)
        except ExecutionAttemptConflict as exc:
            return AttemptRecoveryReport(
                session_id,
                AttemptRecoveryDisposition.MANUAL_REVIEW,
                (str(exc),),
                None,
                expected.digest,
                False,
            )
        if stored is None:
            return AttemptRecoveryReport(
                session_id,
                AttemptRecoveryDisposition.NO_ATTEMPT,
                ("no execution attempt is indexed for session",),
                None,
                expected.digest,
                True,
            )
        attempt = stored.attempt
        mismatches = self._mismatches(attempt, expected)
        if mismatches:
            return AttemptRecoveryReport(
                session_id,
                AttemptRecoveryDisposition.MANUAL_REVIEW,
                mismatches,
                attempt,
                expected.digest,
                False,
            )
        disposition, reasons = self._classify(attempt)
        return AttemptRecoveryReport(
            session_id,
            disposition,
            reasons,
            attempt,
            expected.digest,
            True,
        )

    def require_no_ambiguous_side_effects(
        self,
        session_id: str,
        *,
        expectation: AttemptRecoveryExpectation | None = None,
    ) -> AttemptRecoveryReport:
        report = self.inspect(
            session_id,
            expectation=expectation,
        )
        if report.disposition in {
            AttemptRecoveryDisposition.VERIFY,
            AttemptRecoveryDisposition.MANUAL_REVIEW,
        }:
            raise RuntimeError("; ".join(report.reasons))
        return report
