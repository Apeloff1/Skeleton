"""P1 autonomy-level and de-escalation qualification.

This module does not own execution state.  It qualifies one requested autonomy
transition against the accepted AUTO-02 delegation, explicit safety signals,
and (for escalation only) an exact independent authorization.  Uncertainty,
failure, policy violation, invalid delegation, or human interrupt can only
reduce authority; they can never silently widen it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
import hashlib
import math
from typing import Any, Iterable

from skeleton.automation.agents.delegation_qualification import AgentDelegationDecision
from skeleton.contracts.canonical import (
    CanonicalContractError,
    EvidenceRef,
    canonical_json_bytes,
    evidence_ref_identity,
)


AUTONOMY_CONTROL_SCHEMA_VERSION = 1
AUTONOMY_CONTROL_TASK_ID = "P1-AUTO-03"
AUTONOMY_CONTROL_ACCOUNTABILITY_ID = "ACC-P1-AUTO-03"


class AutonomyControlError(ValueError):
    """Autonomy transition evidence is malformed."""


class AutonomyLevel(IntEnum):
    OBSERVE = 0
    SUGGEST = 1
    ASSISTED = 2
    DELEGATED = 3
    AUTONOMOUS = 4


class TransitionDisposition(str, Enum):
    HOLD = "hold"
    APPLY = "apply"
    FORCED_DEESCALATION = "forced_deescalation"
    BLOCKED = "blocked"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutonomyControlError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise AutonomyControlError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AutonomyControlError(f"{field} must be lowercase sha256")
    return text


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutonomyControlError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AutonomyControlError(f"{field} must be finite numeric")
    return result


def _unit(value: object, field: str) -> float:
    result = _finite(value, field)
    if not 0.0 <= result <= 1.0:
        raise AutonomyControlError(f"{field} must be within [0, 1]")
    return result


def _canonical_digest(value: object) -> str:
    try:
        encoded = canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise AutonomyControlError("autonomy payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _refs(values: Iterable[EvidenceRef], field: str) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise AutonomyControlError(f"{field} must contain EvidenceRef")
    by_identity: dict[str, EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise AutonomyControlError(f"{field} must contain EvidenceRef")
        _text(item.source, f"{field}.source")
        _sha256(item.digest, f"{field}.digest")
        _text(item.category, f"{field}.category", maximum=128)
        by_identity[evidence_ref_identity(item)] = item
    if not by_identity:
        raise AutonomyControlError(f"{field} requires materialized evidence")
    return tuple(by_identity[key] for key in sorted(by_identity))


def _refs_payload(values: tuple[EvidenceRef, ...]) -> list[dict[str, str]]:
    return [
        {
            "identity": evidence_ref_identity(item),
            "source": item.source,
            "digest": item.digest,
            "category": item.category,
        }
        for item in values
    ]


@dataclass(frozen=True, slots=True)
class AutonomyState:
    operation_id: str
    execution_id: str
    agent_id: str
    level: AutonomyLevel
    delegation_digest: str
    version: int

    def __post_init__(self) -> None:
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        try:
            object.__setattr__(self, "level", AutonomyLevel(self.level))
        except ValueError as exc:
            raise AutonomyControlError("invalid autonomy level") from exc
        object.__setattr__(
            self,
            "delegation_digest",
            _sha256(self.delegation_digest, "delegation_digest"),
        )
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version < 1
        ):
            raise AutonomyControlError("version must be a positive integer")

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "level": int(self.level),
            "delegation_digest": self.delegation_digest,
            "version": self.version,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AutonomySignal:
    uncertainty: float = 0.0
    failure_count: int = 0
    verification_failed: bool = False
    environment_degraded: bool = False
    policy_violation: bool = False
    human_interrupt: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "uncertainty", _unit(self.uncertainty, "uncertainty"))
        if (
            isinstance(self.failure_count, bool)
            or not isinstance(self.failure_count, int)
            or self.failure_count < 0
        ):
            raise AutonomyControlError("failure_count must be a non-negative integer")
        for field in (
            "verification_failed",
            "environment_degraded",
            "policy_violation",
            "human_interrupt",
        ):
            if not isinstance(getattr(self, field), bool):
                raise AutonomyControlError(f"{field} must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "uncertainty": self.uncertainty,
            "failure_count": self.failure_count,
            "verification_failed": self.verification_failed,
            "environment_degraded": self.environment_degraded,
            "policy_violation": self.policy_violation,
            "human_interrupt": self.human_interrupt,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AutonomyPolicy:
    max_level: AutonomyLevel = AutonomyLevel.AUTONOMOUS
    medium_uncertainty: float = 0.50
    high_uncertainty: float = 0.75
    failure_assisted_threshold: int = 1
    failure_suggest_threshold: int = 2
    max_escalation_step: int = 1
    require_independent_authorization: bool = True

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "max_level", AutonomyLevel(self.max_level))
        except ValueError as exc:
            raise AutonomyControlError("invalid maximum autonomy level") from exc
        medium = _unit(self.medium_uncertainty, "medium_uncertainty")
        high = _unit(self.high_uncertainty, "high_uncertainty")
        if not 0.0 < medium < high <= 1.0:
            raise AutonomyControlError(
                "uncertainty thresholds must satisfy 0 < medium < high <= 1"
            )
        object.__setattr__(self, "medium_uncertainty", medium)
        object.__setattr__(self, "high_uncertainty", high)
        for field in ("failure_assisted_threshold", "failure_suggest_threshold"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AutonomyControlError(f"{field} must be a positive integer")
        if self.failure_suggest_threshold <= self.failure_assisted_threshold:
            raise AutonomyControlError(
                "failure_suggest_threshold must exceed assisted threshold"
            )
        if (
            isinstance(self.max_escalation_step, bool)
            or not isinstance(self.max_escalation_step, int)
            or self.max_escalation_step < 1
        ):
            raise AutonomyControlError("max_escalation_step must be positive")
        if not isinstance(self.require_independent_authorization, bool):
            raise AutonomyControlError(
                "require_independent_authorization must be boolean"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "max_level": int(self.max_level),
            "medium_uncertainty": self.medium_uncertainty,
            "high_uncertainty": self.high_uncertainty,
            "failure_assisted_threshold": self.failure_assisted_threshold,
            "failure_suggest_threshold": self.failure_suggest_threshold,
            "max_escalation_step": self.max_escalation_step,
            "require_independent_authorization": self.require_independent_authorization,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AutonomyAuthorization:
    operation_id: str
    execution_id: str
    agent_id: str
    from_level: AutonomyLevel
    to_level: AutonomyLevel
    delegation_digest: str
    issuer_id: str
    issuer_digest: str
    expires_at: float
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool = True

    def __post_init__(self) -> None:
        for field in ("operation_id", "execution_id", "agent_id", "issuer_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in ("from_level", "to_level"):
            try:
                object.__setattr__(self, field, AutonomyLevel(getattr(self, field)))
            except ValueError as exc:
                raise AutonomyControlError(f"invalid {field}") from exc
        if self.to_level <= self.from_level:
            raise AutonomyControlError("authorization must describe escalation")
        object.__setattr__(
            self,
            "delegation_digest",
            _sha256(self.delegation_digest, "delegation_digest"),
        )
        object.__setattr__(
            self, "issuer_digest", _sha256(self.issuer_digest, "issuer_digest")
        )
        expiry = _finite(self.expires_at, "expires_at")
        if expiry <= 0:
            raise AutonomyControlError("expires_at must be positive")
        object.__setattr__(self, "expires_at", expiry)
        if not isinstance(self.independent, bool):
            raise AutonomyControlError("independent must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "authorization evidence"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "from_level": int(self.from_level),
            "to_level": int(self.to_level),
            "delegation_digest": self.delegation_digest,
            "issuer_id": self.issuer_id,
            "issuer_digest": self.issuer_digest,
            "expires_at": self.expires_at,
            "independent": self.independent,
            "evidence_refs": _refs_payload(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AutonomyTransitionDecision:
    accepted: bool
    disposition: TransitionDisposition
    from_level: AutonomyLevel
    requested_level: AutonomyLevel
    next_level: AutonomyLevel
    reasons: tuple[str, ...]
    state_digest: str
    signal_digest: str
    policy_digest: str
    delegation_digest: str
    authorization_digest: str | None
    task_id: str = AUTONOMY_CONTROL_TASK_ID
    accountability_id: str = AUTONOMY_CONTROL_ACCOUNTABILITY_ID
    schema_version: int = AUTONOMY_CONTROL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise AutonomyControlError("accepted must be boolean")
        try:
            object.__setattr__(
                self, "disposition", TransitionDisposition(self.disposition)
            )
            for field in ("from_level", "requested_level", "next_level"):
                object.__setattr__(
                    self, field, AutonomyLevel(getattr(self, field))
                )
        except ValueError as exc:
            raise AutonomyControlError("invalid transition enum value") from exc
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise AutonomyControlError("reasons must contain non-empty strings")
        for field in (
            "state_digest",
            "signal_digest",
            "policy_digest",
            "delegation_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        if self.authorization_digest is not None:
            object.__setattr__(
                self,
                "authorization_digest",
                _sha256(self.authorization_digest, "authorization_digest"),
            )
        if self.task_id != AUTONOMY_CONTROL_TASK_ID:
            raise AutonomyControlError("task_id drift")
        if self.accountability_id != AUTONOMY_CONTROL_ACCOUNTABILITY_ID:
            raise AutonomyControlError("accountability_id drift")
        if self.schema_version != AUTONOMY_CONTROL_SCHEMA_VERSION:
            raise AutonomyControlError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "disposition": self.disposition.value,
            "from_level": int(self.from_level),
            "requested_level": int(self.requested_level),
            "next_level": int(self.next_level),
            "reasons": list(self.reasons),
            "state_digest": self.state_digest,
            "signal_digest": self.signal_digest,
            "policy_digest": self.policy_digest,
            "delegation_digest": self.delegation_digest,
            "authorization_digest": self.authorization_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-03:autonomy-deescalation",
    ) -> EvidenceRef:
        if not self.accepted:
            raise AutonomyControlError(
                "blocked autonomy transition cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="autonomy_transition_qualification",
        )


def _safety_ceiling(
    signal: AutonomySignal,
    policy: AutonomyPolicy,
    *,
    delegation_valid: bool,
) -> tuple[AutonomyLevel, list[str]]:
    ceiling = policy.max_level
    reasons: list[str] = []
    if policy.max_level < AutonomyLevel.AUTONOMOUS:
        reasons.append("policy-max-level")

    if not delegation_valid:
        ceiling = AutonomyLevel.OBSERVE
        reasons.append("delegation-invalid")

    if signal.human_interrupt:
        ceiling = min(ceiling, AutonomyLevel.OBSERVE)
        reasons.append("human-interrupt")
    if signal.policy_violation:
        ceiling = min(ceiling, AutonomyLevel.OBSERVE)
        reasons.append("policy-violation")

    if signal.failure_count >= policy.failure_suggest_threshold:
        ceiling = min(ceiling, AutonomyLevel.SUGGEST)
        reasons.append("repeated-failure")
    elif signal.failure_count >= policy.failure_assisted_threshold:
        ceiling = min(ceiling, AutonomyLevel.ASSISTED)
        reasons.append("execution-failure")

    if signal.uncertainty >= policy.high_uncertainty:
        ceiling = min(ceiling, AutonomyLevel.SUGGEST)
        reasons.append("high-uncertainty")
    elif signal.uncertainty >= policy.medium_uncertainty:
        ceiling = min(ceiling, AutonomyLevel.ASSISTED)
        reasons.append("elevated-uncertainty")

    if signal.verification_failed:
        ceiling = min(ceiling, AutonomyLevel.ASSISTED)
        reasons.append("verification-failed")
    if signal.environment_degraded:
        ceiling = min(ceiling, AutonomyLevel.ASSISTED)
        reasons.append("environment-degraded")

    return AutonomyLevel(ceiling), reasons


def _authorization_reasons(
    authorization: AutonomyAuthorization | None,
    *,
    state: AutonomyState,
    requested: AutonomyLevel,
    delegation_digest: str,
    observed_at: float,
    policy: AutonomyPolicy,
) -> list[str]:
    if authorization is None:
        return ["escalation-authorization-missing"]
    reasons: list[str] = []
    if authorization.operation_id != state.operation_id:
        reasons.append("authorization-operation-mismatch")
    if authorization.execution_id != state.execution_id:
        reasons.append("authorization-execution-mismatch")
    if authorization.agent_id != state.agent_id:
        reasons.append("authorization-agent-mismatch")
    if authorization.from_level is not state.level:
        reasons.append("authorization-from-level-mismatch")
    if authorization.to_level is not requested:
        reasons.append("authorization-to-level-mismatch")
    if authorization.delegation_digest != delegation_digest:
        reasons.append("authorization-delegation-mismatch")
    if observed_at >= authorization.expires_at:
        reasons.append("authorization-expired")
    if policy.require_independent_authorization and not authorization.independent:
        reasons.append("authorization-not-independent")
    return reasons


def evaluate_autonomy_transition(
    *,
    state: AutonomyState,
    requested_level: AutonomyLevel,
    signal: AutonomySignal,
    delegation: AgentDelegationDecision,
    observed_at: float,
    authorization: AutonomyAuthorization | None = None,
    policy: AutonomyPolicy | None = None,
) -> AutonomyTransitionDecision:
    if not isinstance(state, AutonomyState):
        raise TypeError("state must be AutonomyState")
    if not isinstance(signal, AutonomySignal):
        raise TypeError("signal must be AutonomySignal")
    if not isinstance(delegation, AgentDelegationDecision):
        raise TypeError("delegation must be AgentDelegationDecision")
    now = _finite(observed_at, "observed_at")
    if now <= 0:
        raise AutonomyControlError("observed_at must be positive")
    try:
        requested = AutonomyLevel(requested_level)
    except ValueError as exc:
        raise AutonomyControlError("invalid requested autonomy level") from exc
    active_policy = policy or AutonomyPolicy()
    if not isinstance(active_policy, AutonomyPolicy):
        raise TypeError("policy must be AutonomyPolicy")
    if authorization is not None and not isinstance(
        authorization, AutonomyAuthorization
    ):
        raise TypeError("authorization must be AutonomyAuthorization")

    delegation_digest = delegation.decision_digest
    delegation_valid = (
        delegation.accepted and state.delegation_digest == delegation_digest
    )
    ceiling, safety_reasons = _safety_ceiling(
        signal,
        active_policy,
        delegation_valid=delegation_valid,
    )

    # Safety signals dominate every request and can only reduce authority.
    if ceiling < state.level:
        next_level = AutonomyLevel(min(int(requested), int(ceiling)))
        reasons = tuple(sorted(set(safety_reasons)))
        return AutonomyTransitionDecision(
            accepted=True,
            disposition=TransitionDisposition.FORCED_DEESCALATION,
            from_level=state.level,
            requested_level=requested,
            next_level=next_level,
            reasons=reasons,
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    if requested > active_policy.max_level:
        return AutonomyTransitionDecision(
            accepted=False,
            disposition=TransitionDisposition.BLOCKED,
            from_level=state.level,
            requested_level=requested,
            next_level=state.level,
            reasons=("requested-level-exceeds-policy",),
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    if requested < state.level:
        return AutonomyTransitionDecision(
            accepted=True,
            disposition=TransitionDisposition.APPLY,
            from_level=state.level,
            requested_level=requested,
            next_level=requested,
            reasons=(),
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    if requested == state.level:
        return AutonomyTransitionDecision(
            accepted=True,
            disposition=TransitionDisposition.HOLD,
            from_level=state.level,
            requested_level=requested,
            next_level=state.level,
            reasons=(),
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    if not delegation_valid:
        # With level OBSERVE there is no lower level to force; fail closed.
        return AutonomyTransitionDecision(
            accepted=False,
            disposition=TransitionDisposition.BLOCKED,
            from_level=state.level,
            requested_level=requested,
            next_level=state.level,
            reasons=("delegation-invalid",),
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    if int(requested) - int(state.level) > active_policy.max_escalation_step:
        return AutonomyTransitionDecision(
            accepted=False,
            disposition=TransitionDisposition.BLOCKED,
            from_level=state.level,
            requested_level=requested,
            next_level=state.level,
            reasons=("escalation-step-too-large",),
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    auth_reasons = _authorization_reasons(
        authorization,
        state=state,
        requested=requested,
        delegation_digest=delegation_digest,
        observed_at=now,
        policy=active_policy,
    )
    if auth_reasons:
        return AutonomyTransitionDecision(
            accepted=False,
            disposition=TransitionDisposition.BLOCKED,
            from_level=state.level,
            requested_level=requested,
            next_level=state.level,
            reasons=tuple(sorted(set(auth_reasons))),
            state_digest=state.digest,
            signal_digest=signal.digest,
            policy_digest=active_policy.digest,
            delegation_digest=delegation_digest,
            authorization_digest=(
                None if authorization is None else authorization.digest
            ),
        )

    return AutonomyTransitionDecision(
        accepted=True,
        disposition=TransitionDisposition.APPLY,
        from_level=state.level,
        requested_level=requested,
        next_level=requested,
        reasons=(),
        state_digest=state.digest,
        signal_digest=signal.digest,
        policy_digest=active_policy.digest,
        delegation_digest=delegation_digest,
        authorization_digest=authorization.digest if authorization else None,
    )


__all__ = [
    "AUTONOMY_CONTROL_ACCOUNTABILITY_ID",
    "AUTONOMY_CONTROL_SCHEMA_VERSION",
    "AUTONOMY_CONTROL_TASK_ID",
    "AutonomyAuthorization",
    "AutonomyControlError",
    "AutonomyLevel",
    "AutonomyPolicy",
    "AutonomySignal",
    "AutonomyState",
    "AutonomyTransitionDecision",
    "TransitionDisposition",
    "evaluate_autonomy_transition",
]
