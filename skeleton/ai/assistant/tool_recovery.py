"""Deterministic recovery decisions for canonical assistant tool receipts.

The assistant never retries consequential side effects merely because a caller
timed out.  This module turns durable receipt evidence into a non-executing
recovery decision that can be consumed by the turn runtime and canonical tool
runtime.

Unknown writes reconcile first.  A write is retryable only when durable
evidence proves the prior attempt did not commit and the request is
idempotency-bound.  Security-sensitive retries require renewed user authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any

from .contracts import SideEffectClass


TOOL_RECOVERY_SCHEMA_VERSION = 1
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#@-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ToolRecoveryError(ValueError):
    """Tool recovery evidence is malformed or internally contradictory."""


class PriorToolOutcome(str, Enum):
    NOT_STARTED = "not_started"
    SUCCEEDED = "succeeded"
    KNOWN_FAILURE = "known_failure"
    UNKNOWN = "unknown"


class ToolRecoveryAction(str, Enum):
    EXECUTE_ORIGINAL = "execute_original"
    RETURN_RECEIPT = "return_receipt"
    RETRY_READ_ONLY = "retry_read_only"
    RETRY_IDEMPOTENT = "retry_idempotent"
    RECONCILE = "reconcile"
    COMPENSATE = "compensate"
    REQUIRE_REAUTHORIZATION = "require_reauthorization"
    QUARANTINE = "quarantine"
    TERMINAL_FAILURE = "terminal_failure"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ToolRecoveryError("value is not canonical-json encodable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ToolRecoveryError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ToolRecoveryError(f"{field} must be lowercase sha256")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ToolRecoveryError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class ToolRecoveryEvidence:
    operation_id: str
    request_digest: str
    proposal_id: str
    capability_id: str
    arguments_digest: str
    side_effect: SideEffectClass | str
    prior_outcome: PriorToolOutcome | str
    durable_receipt: bool
    receipt_status: str | None
    receipt_request_digest: str | None
    receipt_arguments_digest: str | None
    effect_may_have_started: bool
    idempotency_key_present: bool
    reconciliation_available: bool
    compensation_available: bool
    explicit_user_authority_valid: bool
    retry_budget_remaining: int
    downstream_failure: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _token(self.operation_id, "operation_id"))
        object.__setattr__(self, "request_digest", _sha(self.request_digest, "request_digest"))
        object.__setattr__(self, "proposal_id", _token(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "capability_id", _token(self.capability_id, "capability_id"))
        object.__setattr__(
            self, "arguments_digest", _sha(self.arguments_digest, "arguments_digest")
        )
        try:
            object.__setattr__(self, "side_effect", SideEffectClass(self.side_effect))
        except ValueError as exc:
            raise ToolRecoveryError("invalid side-effect class") from exc
        try:
            object.__setattr__(self, "prior_outcome", PriorToolOutcome(self.prior_outcome))
        except ValueError as exc:
            raise ToolRecoveryError("invalid prior tool outcome") from exc
        for field in (
            "durable_receipt",
            "effect_may_have_started",
            "idempotency_key_present",
            "reconciliation_available",
            "compensation_available",
            "explicit_user_authority_valid",
            "downstream_failure",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ToolRecoveryError(f"{field} must be boolean")
        if self.receipt_status is not None:
            if self.receipt_status not in {"succeeded", "failed", "blocked"}:
                raise ToolRecoveryError("invalid receipt_status")
        if self.receipt_request_digest is not None:
            object.__setattr__(
                self,
                "receipt_request_digest",
                _sha(self.receipt_request_digest, "receipt_request_digest"),
            )
        if self.receipt_arguments_digest is not None:
            object.__setattr__(
                self,
                "receipt_arguments_digest",
                _sha(self.receipt_arguments_digest, "receipt_arguments_digest"),
            )
        object.__setattr__(
            self,
            "retry_budget_remaining",
            _nonnegative_int(self.retry_budget_remaining, "retry_budget_remaining"),
        )
        if self.durable_receipt and self.receipt_status is None:
            raise ToolRecoveryError("durable receipt requires receipt_status")
        if not self.durable_receipt and (
            self.receipt_request_digest is not None
            or self.receipt_arguments_digest is not None
            or self.receipt_status is not None
        ):
            raise ToolRecoveryError("receipt fields require durable_receipt")

    @property
    def is_read_only(self) -> bool:
        return self.side_effect in {SideEffectClass.NONE, SideEffectClass.READ_ONLY}

    @property
    def is_security_sensitive(self) -> bool:
        return self.side_effect is SideEffectClass.SECURITY_SENSITIVE

    @property
    def is_reversible(self) -> bool:
        return self.side_effect is SideEffectClass.REVERSIBLE_WRITE

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": TOOL_RECOVERY_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "request_digest": self.request_digest,
            "proposal_id": self.proposal_id,
            "capability_id": self.capability_id,
            "arguments_digest": self.arguments_digest,
            "side_effect": self.side_effect.value,
            "prior_outcome": self.prior_outcome.value,
            "durable_receipt": self.durable_receipt,
            "receipt_status": self.receipt_status,
            "receipt_request_digest": self.receipt_request_digest,
            "receipt_arguments_digest": self.receipt_arguments_digest,
            "effect_may_have_started": self.effect_may_have_started,
            "idempotency_key_present": self.idempotency_key_present,
            "reconciliation_available": self.reconciliation_available,
            "compensation_available": self.compensation_available,
            "explicit_user_authority_valid": self.explicit_user_authority_valid,
            "retry_budget_remaining": self.retry_budget_remaining,
            "downstream_failure": self.downstream_failure,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class ToolRecoveryDecision:
    action: ToolRecoveryAction | str
    reasons: tuple[str, ...]
    evidence_digest: str
    retry_consumes_budget: bool = False
    terminal: bool = False
    authority_scope: str = "tool-recovery-decision-only"
    production_authority: bool = False
    schema_version: int = TOOL_RECOVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "action", ToolRecoveryAction(self.action))
        except ValueError as exc:
            raise ToolRecoveryError("invalid recovery action") from exc
        if not isinstance(self.reasons, tuple) or not self.reasons or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ToolRecoveryError("recovery decision requires reason codes")
        object.__setattr__(self, "evidence_digest", _sha(self.evidence_digest, "evidence_digest"))
        if not isinstance(self.retry_consumes_budget, bool):
            raise ToolRecoveryError("retry_consumes_budget must be boolean")
        if not isinstance(self.terminal, bool):
            raise ToolRecoveryError("terminal must be boolean")
        if self.authority_scope != "tool-recovery-decision-only":
            raise ToolRecoveryError("tool recovery authority scope escalation")
        if self.production_authority is not False:
            raise ToolRecoveryError("tool recovery decision cannot execute side effects")
        if self.schema_version != TOOL_RECOVERY_SCHEMA_VERSION:
            raise ToolRecoveryError("unsupported tool recovery schema")
        retry_actions = {
            ToolRecoveryAction.RETRY_READ_ONLY,
            ToolRecoveryAction.RETRY_IDEMPOTENT,
        }
        if self.retry_consumes_budget != (self.action in retry_actions):
            raise ToolRecoveryError("retry budget accounting does not match recovery action")
        if self.terminal != (self.action is ToolRecoveryAction.TERMINAL_FAILURE):
            raise ToolRecoveryError("terminal flag does not match recovery action")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action.value,
            "reasons": list(self.reasons),
            "evidence_digest": self.evidence_digest,
            "retry_consumes_budget": self.retry_consumes_budget,
            "terminal": self.terminal,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def decision_digest(self) -> str:
        return _digest(self.payload())


def _decision(
    evidence: ToolRecoveryEvidence,
    action: ToolRecoveryAction,
    *reasons: str,
) -> ToolRecoveryDecision:
    return ToolRecoveryDecision(
        action=action,
        reasons=tuple(reasons),
        evidence_digest=evidence.digest,
        retry_consumes_budget=action
        in {ToolRecoveryAction.RETRY_READ_ONLY, ToolRecoveryAction.RETRY_IDEMPOTENT},
        terminal=action is ToolRecoveryAction.TERMINAL_FAILURE,
    )


def decide_tool_recovery(evidence: ToolRecoveryEvidence) -> ToolRecoveryDecision:
    """Produce one fail-closed recovery action from durable evidence."""

    if not isinstance(evidence, ToolRecoveryEvidence):
        raise TypeError("evidence must be ToolRecoveryEvidence")

    if evidence.durable_receipt:
        if evidence.receipt_request_digest != evidence.request_digest:
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "receipt-request-binding-mismatch",
            )
        if evidence.receipt_arguments_digest != evidence.arguments_digest:
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "receipt-arguments-binding-mismatch",
            )
        expected = {
            PriorToolOutcome.SUCCEEDED: "succeeded",
            PriorToolOutcome.KNOWN_FAILURE: "failed",
        }.get(evidence.prior_outcome)
        if expected is not None:
            blocked_failure = (
                evidence.prior_outcome is PriorToolOutcome.KNOWN_FAILURE
                and evidence.receipt_status == "blocked"
            )
            if evidence.receipt_status != expected and not blocked_failure:
                return _decision(
                    evidence,
                    ToolRecoveryAction.QUARANTINE,
                    "receipt-outcome-contradiction",
                )

    if evidence.prior_outcome is PriorToolOutcome.NOT_STARTED:
        if evidence.durable_receipt:
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "not-started-contradicts-durable-receipt",
            )
        if evidence.effect_may_have_started:
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "not-started-contradicts-effect-started",
            )
        return _decision(
            evidence,
            ToolRecoveryAction.EXECUTE_ORIGINAL,
            "no-prior-attempt",
        )

    if evidence.prior_outcome is PriorToolOutcome.SUCCEEDED:
        if not evidence.is_read_only and not evidence.durable_receipt:
            if evidence.reconciliation_available:
                return _decision(
                    evidence,
                    ToolRecoveryAction.RECONCILE,
                    "successful-write-lacks-durable-receipt",
                )
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "successful-write-lacks-durable-receipt",
                "reconciliation-unavailable",
            )
        if evidence.downstream_failure and evidence.is_reversible:
            if evidence.compensation_available:
                return _decision(
                    evidence,
                    ToolRecoveryAction.COMPENSATE,
                    "downstream-failure-after-reversible-write",
                )
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "reversible-write-needs-compensation",
                "compensation-unavailable",
            )
        return _decision(
            evidence,
            ToolRecoveryAction.RETURN_RECEIPT,
            "durable-success-already-established"
            if evidence.durable_receipt
            else "read-only-success-already-established",
        )

    if evidence.prior_outcome is PriorToolOutcome.UNKNOWN:
        if evidence.durable_receipt:
            return _decision(
                evidence,
                ToolRecoveryAction.QUARANTINE,
                "unknown-outcome-contradicts-durable-receipt",
            )
        if evidence.is_read_only:
            if evidence.retry_budget_remaining > 0:
                return _decision(
                    evidence,
                    ToolRecoveryAction.RETRY_READ_ONLY,
                    "read-only-outcome-unknown",
                )
            return _decision(
                evidence,
                ToolRecoveryAction.TERMINAL_FAILURE,
                "read-only-outcome-unknown",
                "retry-budget-exhausted",
            )
        if evidence.reconciliation_available:
            return _decision(
                evidence,
                ToolRecoveryAction.RECONCILE,
                "consequential-outcome-unknown",
            )
        return _decision(
            evidence,
            ToolRecoveryAction.QUARANTINE,
            "consequential-outcome-unknown",
            "reconciliation-unavailable",
        )

    # Known failure.
    if evidence.effect_may_have_started:
        if evidence.is_reversible and evidence.compensation_available:
            return _decision(
                evidence,
                ToolRecoveryAction.COMPENSATE,
                "failed-reversible-write-may-have-started",
            )
        if evidence.reconciliation_available:
            return _decision(
                evidence,
                ToolRecoveryAction.RECONCILE,
                "failed-write-may-have-started",
            )
        return _decision(
            evidence,
            ToolRecoveryAction.QUARANTINE,
            "failed-write-may-have-started",
            "reconciliation-unavailable",
        )

    if evidence.retry_budget_remaining < 1:
        return _decision(
            evidence,
            ToolRecoveryAction.TERMINAL_FAILURE,
            "known-failure",
            "retry-budget-exhausted",
        )

    if evidence.is_read_only:
        return _decision(
            evidence,
            ToolRecoveryAction.RETRY_READ_ONLY,
            "known-read-only-failure",
        )

    if not evidence.durable_receipt:
        return _decision(
            evidence,
            ToolRecoveryAction.QUARANTINE,
            "write-retry-requires-durable-failure-receipt",
        )
    if evidence.receipt_status == "blocked":
        return _decision(
            evidence,
            ToolRecoveryAction.TERMINAL_FAILURE,
            "canonical-runtime-blocked-request",
        )
    if not evidence.idempotency_key_present:
        return _decision(
            evidence,
            ToolRecoveryAction.QUARANTINE,
            "write-retry-requires-idempotency-key",
        )
    if evidence.is_security_sensitive and not evidence.explicit_user_authority_valid:
        return _decision(
            evidence,
            ToolRecoveryAction.REQUIRE_REAUTHORIZATION,
            "security-sensitive-retry-requires-fresh-user-authority",
        )
    return _decision(
        evidence,
        ToolRecoveryAction.RETRY_IDEMPOTENT,
        "durable-known-failure-proves-no-commit",
        "idempotency-binding-present",
    )


__all__ = [
    "TOOL_RECOVERY_SCHEMA_VERSION",
    "PriorToolOutcome",
    "ToolRecoveryAction",
    "ToolRecoveryDecision",
    "ToolRecoveryError",
    "ToolRecoveryEvidence",
    "decide_tool_recovery",
]
