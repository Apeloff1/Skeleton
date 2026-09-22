"""Canonical operation identity and lifecycle contracts for assembled AI work.

An operation is the user-visible unit of durable work. This module is deliberately
transport- and storage-neutral so API, orchestration, queue, tool, provider, and
stream implementations can share one state machine.

The contract makes three properties explicit:
- idempotency identity is distinct from tracing identity;
- deadlines are part of the operation contract, not an adapter-local timeout;
- only declared state transitions are legal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any
from uuid import UUID


class OperationContractError(ValueError):
    """Raised when an operation envelope violates the canonical lifecycle."""


class OperationTransitionError(OperationContractError):
    """Raised when an operation attempts an illegal state transition."""


class OperationState(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    ADMITTED = "admitted"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_TOOL = "waiting_for_tool"
    WAITING_FOR_USER = "waiting_for_user"
    RETRYING = "retrying"
    DEGRADED = "degraded"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_OPERATION_STATES = frozenset(
    {
        OperationState.COMPLETED,
        OperationState.FAILED,
        OperationState.CANCELLED,
    }
)

_ALLOWED_TRANSITIONS: dict[OperationState, frozenset[OperationState]] = {
    OperationState.CREATED: frozenset(
        {OperationState.VALIDATED, OperationState.FAILED, OperationState.CANCELLED}
    ),
    OperationState.VALIDATED: frozenset(
        {OperationState.AUTHORIZED, OperationState.FAILED, OperationState.CANCELLED}
    ),
    OperationState.AUTHORIZED: frozenset(
        {OperationState.ADMITTED, OperationState.FAILED, OperationState.CANCELLED}
    ),
    OperationState.ADMITTED: frozenset(
        {
            OperationState.QUEUED,
            OperationState.RUNNING,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
    ),
    OperationState.QUEUED: frozenset(
        {OperationState.RUNNING, OperationState.FAILED, OperationState.CANCELLED}
    ),
    OperationState.RUNNING: frozenset(
        {
            OperationState.WAITING_FOR_TOOL,
            OperationState.WAITING_FOR_USER,
            OperationState.RETRYING,
            OperationState.DEGRADED,
            OperationState.COMPLETED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
    ),
    OperationState.WAITING_FOR_TOOL: frozenset(
        {
            OperationState.RUNNING,
            OperationState.RETRYING,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
    ),
    OperationState.WAITING_FOR_USER: frozenset(
        {OperationState.RUNNING, OperationState.FAILED, OperationState.CANCELLED}
    ),
    OperationState.RETRYING: frozenset(
        {
            OperationState.RUNNING,
            OperationState.DEGRADED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
    ),
    OperationState.DEGRADED: frozenset(
        {
            OperationState.RUNNING,
            OperationState.RETRYING,
            OperationState.COMPLETED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
    ),
    OperationState.COMPLETED: frozenset(),
    OperationState.FAILED: frozenset(),
    OperationState.CANCELLED: frozenset(),
}


def _normalized_text(value: str, field_name: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperationContractError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise OperationContractError(f"{field_name} must be normalized")
    if len(normalized) > max_length:
        raise OperationContractError(f"{field_name} exceeds maximum length")
    return normalized


def _uuid_text(value: str, field_name: str) -> str:
    text = _normalized_text(value, field_name, max_length=64)
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as exc:
        raise OperationContractError(f"{field_name} must be a canonical UUID") from exc
    if str(parsed) != text:
        raise OperationContractError(f"{field_name} must be a canonical UUID")
    return text


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise OperationContractError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise OperationContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class OperationEnvelope:
    operation_id: str
    tenant_id: str
    actor_id: str
    capability: str
    created_at: datetime
    deadline: datetime
    idempotency_key: str
    trace_id: str
    state: OperationState = OperationState.CREATED

    def __post_init__(self) -> None:
        _uuid_text(self.operation_id, "operation_id")
        _normalized_text(self.tenant_id, "tenant_id")
        _normalized_text(self.actor_id, "actor_id")
        _normalized_text(self.capability, "capability")
        created = _aware_utc(self.created_at, "created_at")
        deadline = _aware_utc(self.deadline, "deadline")
        if deadline <= created:
            raise OperationContractError("deadline must be later than created_at")
        _normalized_text(self.idempotency_key, "idempotency_key", max_length=1024)
        _normalized_text(self.trace_id, "trace_id", max_length=256)
        try:
            OperationState(self.state)
        except ValueError as exc:
            raise OperationContractError("state is invalid") from exc

    @property
    def terminal(self) -> bool:
        return OperationState(self.state) in TERMINAL_OPERATION_STATES

    @property
    def identity_digest(self) -> str:
        payload = {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "capability": self.capability,
            "idempotency_key": self.idempotency_key,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def transition(self, target: OperationState | str) -> "OperationEnvelope":
        try:
            target_state = OperationState(target)
        except ValueError as exc:
            raise OperationTransitionError(f"unknown target state: {target!r}") from exc
        current = OperationState(self.state)
        if target_state not in _ALLOWED_TRANSITIONS[current]:
            raise OperationTransitionError(
                f"illegal operation transition: {current.value} -> {target_state.value}"
            )
        return replace(self, state=target_state)

    def expired(self, *, now: datetime | None = None) -> bool:
        instant = _aware_utc(now or datetime.now(timezone.utc), "now")
        return instant >= _aware_utc(self.deadline, "deadline")

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "capability": self.capability,
            "created_at": _aware_utc(self.created_at, "created_at").isoformat(),
            "deadline": _aware_utc(self.deadline, "deadline").isoformat(),
            "idempotency_key": self.idempotency_key,
            "trace_id": self.trace_id,
            "state": OperationState(self.state).value,
            "identity_digest": self.identity_digest,
        }


__all__ = [
    "OperationContractError",
    "OperationEnvelope",
    "OperationState",
    "OperationTransitionError",
    "TERMINAL_OPERATION_STATES",
]
