"""P1 human approval, interrupt, pause/resume, and override qualification.

This module is a non-executing control contract. It binds a human control
command to the exact durable operation/execution/agent identity, current
autonomy state, delegated authority, arguments digest, state version, expiry,
and materialized evidence. Accepted approvals may be converted into the
AUTO-03 AutonomyAuthorization primitive; interrupts, pauses, resumes, and
overrides never widen autonomy by themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from typing import Any, Iterable

from skeleton.automation.agents.autonomy_control import (
    AutonomyAuthorization,
    AutonomyLevel,
    AutonomyState,
)
from skeleton.contracts.canonical import (
    CanonicalContractError,
    EvidenceRef,
    canonical_json_bytes,
    evidence_ref_identity,
)


HUMAN_CONTROL_SCHEMA_VERSION = 1
HUMAN_CONTROL_TASK_ID = "P1-AUTO-04"
HUMAN_CONTROL_ACCOUNTABILITY_ID = "ACC-P1-AUTO-04"


class HumanControlError(ValueError):
    """Human-control evidence or state is malformed."""


class HumanControlAction(str, Enum):
    APPROVE = "approve"
    INTERRUPT = "interrupt"
    PAUSE = "pause"
    RESUME = "resume"
    OVERRIDE = "override"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanControlError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise HumanControlError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise HumanControlError(f"{field} must be lowercase sha256")
    return text


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HumanControlError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise HumanControlError(f"{field} must be finite numeric")
    return result


def _canonical_digest(value: object) -> str:
    try:
        encoded = canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise HumanControlError("human-control payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _refs(values: Iterable[EvidenceRef], field: str) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise HumanControlError(f"{field} must contain EvidenceRef")
    by_identity: dict[str, EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise HumanControlError(f"{field} must contain EvidenceRef")
        _text(item.source, f"{field}.source")
        _sha256(item.digest, f"{field}.digest")
        _text(item.category, f"{field}.category", maximum=128)
        by_identity[evidence_ref_identity(item)] = item
    if not by_identity:
        raise HumanControlError(f"{field} requires materialized evidence")
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
class HumanControlState:
    operation_id: str
    execution_id: str
    agent_id: str
    autonomy_state_digest: str
    authority_digest: str
    level: AutonomyLevel
    paused: bool = False
    interrupted: bool = False
    version: int = 1
    last_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "autonomy_state_digest",
            _sha256(self.autonomy_state_digest, "autonomy_state_digest"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        try:
            object.__setattr__(self, "level", AutonomyLevel(self.level))
        except ValueError as exc:
            raise HumanControlError("invalid autonomy level") from exc
        for field in ("paused", "interrupted"):
            if not isinstance(getattr(self, field), bool):
                raise HumanControlError(f"{field} must be boolean")
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version < 1
        ):
            raise HumanControlError("version must be a positive integer")
        if self.last_receipt_digest is not None:
            object.__setattr__(
                self,
                "last_receipt_digest",
                _sha256(self.last_receipt_digest, "last_receipt_digest"),
            )

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "autonomy_state_digest": self.autonomy_state_digest,
            "authority_digest": self.authority_digest,
            "level": int(self.level),
            "paused": self.paused,
            "interrupted": self.interrupted,
            "version": self.version,
            "last_receipt_digest": self.last_receipt_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class HumanControlCommand:
    operation_id: str
    execution_id: str
    agent_id: str
    action: HumanControlAction
    arguments_digest: str
    authority_digest: str
    state_digest: str
    state_version: int
    issuer_id: str
    issuer_digest: str
    issued_at: float
    expires_at: float
    evidence_refs: tuple[EvidenceRef, ...]
    requested_level: AutonomyLevel | None = None
    independent: bool = True

    def __post_init__(self) -> None:
        for field in ("operation_id", "execution_id", "agent_id", "issuer_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        try:
            object.__setattr__(self, "action", HumanControlAction(self.action))
        except ValueError as exc:
            raise HumanControlError("invalid human-control action") from exc
        for field in (
            "arguments_digest",
            "authority_digest",
            "state_digest",
            "issuer_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        if (
            isinstance(self.state_version, bool)
            or not isinstance(self.state_version, int)
            or self.state_version < 1
        ):
            raise HumanControlError("state_version must be a positive integer")
        issued = _finite(self.issued_at, "issued_at")
        expiry = _finite(self.expires_at, "expires_at")
        if issued <= 0:
            raise HumanControlError("issued_at must be positive")
        if expiry <= issued:
            raise HumanControlError("expires_at must be greater than issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expiry)
        if not isinstance(self.independent, bool):
            raise HumanControlError("independent must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "human-control evidence"),
        )

        needs_level = self.action in {
            HumanControlAction.APPROVE,
            HumanControlAction.OVERRIDE,
        }
        if needs_level and self.requested_level is None:
            raise HumanControlError(
                f"{self.action.value} requires requested_level"
            )
        if not needs_level and self.requested_level is not None:
            raise HumanControlError(
                f"{self.action.value} forbids requested_level"
            )
        if self.requested_level is not None:
            try:
                object.__setattr__(
                    self,
                    "requested_level",
                    AutonomyLevel(self.requested_level),
                )
            except ValueError as exc:
                raise HumanControlError("invalid requested_level") from exc

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "action": self.action.value,
            "arguments_digest": self.arguments_digest,
            "authority_digest": self.authority_digest,
            "state_digest": self.state_digest,
            "state_version": self.state_version,
            "issuer_id": self.issuer_id,
            "issuer_digest": self.issuer_digest,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "evidence_refs": _refs_payload(self.evidence_refs),
            "requested_level": (
                None if self.requested_level is None else int(self.requested_level)
            ),
            "independent": self.independent,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class HumanControlDecision:
    accepted: bool
    action: HumanControlAction
    reasons: tuple[str, ...]
    operation_id: str
    execution_id: str
    agent_id: str
    arguments_digest: str
    state_digest: str
    command_digest: str
    autonomy_state_digest: str
    authority_digest: str
    from_level: AutonomyLevel
    requested_level: AutonomyLevel | None
    next_level: AutonomyLevel
    next_paused: bool
    next_interrupted: bool
    current_version: int
    next_version: int
    issuer_id: str
    issuer_digest: str
    expires_at: float
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool
    observed_at: float
    previous_receipt_digest: str | None
    task_id: str = HUMAN_CONTROL_TASK_ID
    accountability_id: str = HUMAN_CONTROL_ACCOUNTABILITY_ID
    schema_version: int = HUMAN_CONTROL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise HumanControlError("accepted must be boolean")
        try:
            object.__setattr__(self, "action", HumanControlAction(self.action))
            object.__setattr__(self, "from_level", AutonomyLevel(self.from_level))
            object.__setattr__(self, "next_level", AutonomyLevel(self.next_level))
            if self.requested_level is not None:
                object.__setattr__(
                    self,
                    "requested_level",
                    AutonomyLevel(self.requested_level),
                )
        except ValueError as exc:
            raise HumanControlError("invalid decision enum value") from exc
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise HumanControlError("reasons must contain non-empty strings")
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "arguments_digest",
            _sha256(self.arguments_digest, "arguments_digest"),
        )
        for field in (
            "state_digest",
            "command_digest",
            "autonomy_state_digest",
            "authority_digest",
            "issuer_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(self, "issuer_id", _text(self.issuer_id, "issuer_id"))
        for field in ("next_paused", "next_interrupted", "independent"):
            if not isinstance(getattr(self, field), bool):
                raise HumanControlError(f"{field} must be boolean")
        for field in ("current_version", "next_version"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise HumanControlError(f"{field} must be positive")
        if self.accepted:
            if self.next_version != self.current_version + 1:
                raise HumanControlError("accepted decision must advance version exactly once")
        elif self.next_version != self.current_version:
            raise HumanControlError("rejected decision cannot advance version")
        expiry = _finite(self.expires_at, "expires_at")
        observed = _finite(self.observed_at, "observed_at")
        if expiry <= 0 or observed <= 0:
            raise HumanControlError("decision timestamps must be positive")
        object.__setattr__(self, "expires_at", expiry)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "decision evidence"),
        )
        if self.previous_receipt_digest is not None:
            object.__setattr__(
                self,
                "previous_receipt_digest",
                _sha256(self.previous_receipt_digest, "previous_receipt_digest"),
            )
        if self.task_id != HUMAN_CONTROL_TASK_ID:
            raise HumanControlError("task_id drift")
        if self.accountability_id != HUMAN_CONTROL_ACCOUNTABILITY_ID:
            raise HumanControlError("accountability_id drift")
        if self.schema_version != HUMAN_CONTROL_SCHEMA_VERSION:
            raise HumanControlError("unsupported schema version")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "action": self.action.value,
            "reasons": list(self.reasons),
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "arguments_digest": self.arguments_digest,
            "state_digest": self.state_digest,
            "command_digest": self.command_digest,
            "autonomy_state_digest": self.autonomy_state_digest,
            "authority_digest": self.authority_digest,
            "from_level": int(self.from_level),
            "requested_level": (
                None if self.requested_level is None else int(self.requested_level)
            ),
            "next_level": int(self.next_level),
            "next_paused": self.next_paused,
            "next_interrupted": self.next_interrupted,
            "current_version": self.current_version,
            "next_version": self.next_version,
            "issuer_id": self.issuer_id,
            "issuer_digest": self.issuer_digest,
            "expires_at": self.expires_at,
            "evidence_refs": _refs_payload(self.evidence_refs),
            "independent": self.independent,
            "previous_receipt_digest": self.previous_receipt_digest,
        }

    def receipt_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "observed_at": self.observed_at,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.identity_payload())

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.receipt_payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-04:human-control",
    ) -> EvidenceRef:
        if not self.accepted:
            raise HumanControlError(
                "rejected human-control decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.receipt_digest,
            category="human_control_qualification",
        )

    def accepted_autonomy_authorization(self) -> AutonomyAuthorization:
        if not self.accepted or self.action is not HumanControlAction.APPROVE:
            raise HumanControlError(
                "only an accepted approval may become autonomy authorization"
            )
        if self.requested_level is None:
            raise HumanControlError("accepted approval is missing requested level")
        return AutonomyAuthorization(
            operation_id=self.operation_id,
            execution_id=self.execution_id,
            agent_id=self.agent_id,
            from_level=self.from_level,
            to_level=self.requested_level,
            delegation_digest=self.authority_digest,
            issuer_id=self.issuer_id,
            issuer_digest=self.issuer_digest,
            expires_at=self.expires_at,
            evidence_refs=self.evidence_refs,
            independent=self.independent,
        )



def evaluate_human_control(
    *,
    state: HumanControlState,
    command: HumanControlCommand,
    autonomy_state: AutonomyState,
    observed_at: float,
) -> HumanControlDecision:
    """Qualify one exact human-control command without executing it."""

    if not isinstance(state, HumanControlState):
        raise TypeError("state must be HumanControlState")
    if not isinstance(command, HumanControlCommand):
        raise TypeError("command must be HumanControlCommand")
    if not isinstance(autonomy_state, AutonomyState):
        raise TypeError("autonomy_state must be AutonomyState")
    now = _finite(observed_at, "observed_at")
    if now <= 0:
        raise HumanControlError("observed_at must be positive")

    reasons: list[str] = []

    if autonomy_state.operation_id != state.operation_id:
        reasons.append("autonomy-operation-mismatch")
    if autonomy_state.execution_id != state.execution_id:
        reasons.append("autonomy-execution-mismatch")
    if autonomy_state.agent_id != state.agent_id:
        reasons.append("autonomy-agent-mismatch")
    if autonomy_state.digest != state.autonomy_state_digest:
        reasons.append("autonomy-state-digest-mismatch")
    if autonomy_state.delegation_digest != state.authority_digest:
        reasons.append("autonomy-authority-mismatch")
    if autonomy_state.level is not state.level:
        reasons.append("autonomy-level-mismatch")

    if command.operation_id != state.operation_id:
        reasons.append("command-operation-mismatch")
    if command.execution_id != state.execution_id:
        reasons.append("command-execution-mismatch")
    if command.agent_id != state.agent_id:
        reasons.append("command-agent-mismatch")
    if command.authority_digest != state.authority_digest:
        reasons.append("command-authority-mismatch")
    if command.state_digest != state.digest:
        reasons.append("command-state-digest-mismatch")
    if command.state_version != state.version:
        reasons.append("command-state-version-mismatch")
    if command.issuer_id == state.agent_id:
        reasons.append("issuer-not-independent-of-agent")
    if now < command.issued_at:
        reasons.append("command-not-yet-valid")
    if now >= command.expires_at:
        reasons.append("command-expired")

    next_level = state.level
    next_paused = state.paused
    next_interrupted = state.interrupted

    if command.action is HumanControlAction.APPROVE:
        if state.paused:
            reasons.append("state-paused")
        if state.interrupted:
            reasons.append("state-interrupted")
        if not command.independent:
            reasons.append("approval-not-independent")
        target = command.requested_level
        if target is None or int(target) != int(state.level) + 1:
            reasons.append("approval-not-one-step-escalation")
    elif command.action is HumanControlAction.INTERRUPT:
        next_level = AutonomyLevel.OBSERVE
        next_paused = True
        next_interrupted = True
    elif command.action is HumanControlAction.PAUSE:
        next_level = AutonomyLevel.OBSERVE
        next_paused = True
    elif command.action is HumanControlAction.RESUME:
        if not state.paused:
            reasons.append("state-not-paused")
        next_paused = False
        next_interrupted = False
    elif command.action is HumanControlAction.OVERRIDE:
        target = command.requested_level
        if target is None:
            reasons.append("override-target-missing")
        elif target > state.level:
            reasons.append("override-would-escalate")
        else:
            next_level = target

    normalized = tuple(sorted(set(reasons)))
    accepted = not normalized
    if not accepted:
        next_level = state.level
        next_paused = state.paused
        next_interrupted = state.interrupted

    return HumanControlDecision(
        accepted=accepted,
        action=command.action,
        reasons=normalized,
        operation_id=state.operation_id,
        execution_id=state.execution_id,
        agent_id=state.agent_id,
        arguments_digest=command.arguments_digest,
        state_digest=state.digest,
        command_digest=command.digest,
        autonomy_state_digest=state.autonomy_state_digest,
        authority_digest=state.authority_digest,
        from_level=state.level,
        requested_level=command.requested_level,
        next_level=next_level,
        next_paused=next_paused,
        next_interrupted=next_interrupted,
        current_version=state.version,
        next_version=state.version + 1 if accepted else state.version,
        issuer_id=command.issuer_id,
        issuer_digest=command.issuer_digest,
        expires_at=command.expires_at,
        evidence_refs=command.evidence_refs,
        independent=command.independent,
        observed_at=now,
        previous_receipt_digest=state.last_receipt_digest,
    )


__all__ = [
    "HUMAN_CONTROL_ACCOUNTABILITY_ID",
    "HUMAN_CONTROL_SCHEMA_VERSION",
    "HUMAN_CONTROL_TASK_ID",
    "HumanControlAction",
    "HumanControlCommand",
    "HumanControlDecision",
    "HumanControlError",
    "HumanControlState",
    "evaluate_human_control",
]
