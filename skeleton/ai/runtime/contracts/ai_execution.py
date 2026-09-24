"""Canonical cognitive execution contracts.

Execution records bind one durable operation to context, provider, tool,
verification, memory, artifact, usage, and final-result lineage. They contain
observable state only and are transport/provider neutral.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


AI_EXECUTION_SCHEMA_VERSION = 1
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class AIExecutionContractError(ValueError):
    """A cognitive-execution contract is malformed."""


class ExecutionState(str, Enum):
    CREATED = "created"
    LOADING = "loading"
    ASSEMBLING_CONTEXT = "assembling_context"
    ROUTING = "routing"
    PROVIDER_PENDING = "provider_pending"
    PROVIDER_COMPLETED = "provider_completed"
    CLASSIFYING_OUTPUT = "classifying_output"
    WAITING_FOR_TOOL_AUTHORITY = "waiting_for_tool_authority"
    WAITING_FOR_USER = "waiting_for_user"
    TOOL_PENDING = "tool_pending"
    TOOL_COMPLETED = "tool_completed"
    CHECKPOINTING = "checkpointing"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_EXECUTION_STATES = frozenset(
    {ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED}
)

_ALLOWED_EXECUTION_TRANSITIONS: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.CREATED: frozenset(
        {
            ExecutionState.LOADING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.LOADING: frozenset(
        {
            ExecutionState.ASSEMBLING_CONTEXT,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.ASSEMBLING_CONTEXT: frozenset(
        {
            ExecutionState.ROUTING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.ROUTING: frozenset(
        {
            ExecutionState.PROVIDER_PENDING,
            ExecutionState.DEGRADED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.PROVIDER_PENDING: frozenset(
        {
            ExecutionState.PROVIDER_COMPLETED,
            ExecutionState.DEGRADED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.PROVIDER_COMPLETED: frozenset(
        {
            ExecutionState.CLASSIFYING_OUTPUT,
            ExecutionState.CHECKPOINTING,
            ExecutionState.VERIFYING,
            ExecutionState.FINALIZING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.CLASSIFYING_OUTPUT: frozenset(
        {
            ExecutionState.WAITING_FOR_TOOL_AUTHORITY,
            ExecutionState.TOOL_PENDING,
            ExecutionState.CHECKPOINTING,
            ExecutionState.VERIFYING,
            ExecutionState.FINALIZING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.WAITING_FOR_TOOL_AUTHORITY: frozenset(
        {
            ExecutionState.TOOL_PENDING,
            ExecutionState.WAITING_FOR_USER,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.WAITING_FOR_USER: frozenset(
        {
            ExecutionState.TOOL_PENDING,
            ExecutionState.PROVIDER_PENDING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.TOOL_PENDING: frozenset(
        {
            ExecutionState.TOOL_COMPLETED,
            ExecutionState.WAITING_FOR_USER,
            ExecutionState.DEGRADED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.TOOL_COMPLETED: frozenset(
        {
            ExecutionState.CHECKPOINTING,
            ExecutionState.PROVIDER_PENDING,
            ExecutionState.VERIFYING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.CHECKPOINTING: frozenset(
        {
            ExecutionState.PROVIDER_PENDING,
            ExecutionState.VERIFYING,
            ExecutionState.FINALIZING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.VERIFYING: frozenset(
        {
            ExecutionState.REPAIRING,
            ExecutionState.FINALIZING,
            ExecutionState.DEGRADED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.REPAIRING: frozenset(
        {
            ExecutionState.PROVIDER_PENDING,
            ExecutionState.VERIFYING,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.FINALIZING: frozenset(
        {
            ExecutionState.COMPLETED,
            ExecutionState.DEGRADED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.DEGRADED: frozenset(
        {
            ExecutionState.PROVIDER_PENDING,
            ExecutionState.VERIFYING,
            ExecutionState.FINALIZING,
            ExecutionState.COMPLETED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.COMPLETED: frozenset(),
    ExecutionState.FAILED: frozenset(),
    ExecutionState.CANCELLED: frozenset(),
}


def _text(value: object, field_name: str, *, maximum: int = 65536) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AIExecutionContractError(f"{field_name} must be non-empty text")
    normalized = value.strip()
    if normalized != value:
        raise AIExecutionContractError(f"{field_name} must be normalized")
    if len(normalized) > maximum:
        raise AIExecutionContractError(f"{field_name} exceeds maximum length")
    return normalized


def _optional_text(
    value: object | None, field_name: str, *, maximum: int = 2048
) -> str | None:
    return None if value is None else _text(value, field_name, maximum=maximum)


def _aware(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AIExecutionContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json(value: object, field_name: str, *, max_bytes: int = 512 * 1024) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AIExecutionContractError(f"{field_name} must be an object")
    result = dict(value)
    try:
        encoded = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AIExecutionContractError(
            f"{field_name} must be deterministic JSON"
        ) from exc
    if len(encoded) > max_bytes:
        raise AIExecutionContractError(f"{field_name} exceeds maximum size")
    return result


def _refs(values: Iterable[str], field_name: str, *, maximum: int) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AIExecutionContractError(f"{field_name} must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _text(raw, field_name, maximum=2048)
        if value not in result:
            result.append(value)
        if len(result) > maximum:
            raise AIExecutionContractError(f"{field_name} exceeds maximum count")
    return tuple(result)


def _digest(value: str, field_name: str) -> str:
    normalized = _text(value, field_name, maximum=64)
    if _DIGEST.fullmatch(normalized) is None:
        raise AIExecutionContractError(f"{field_name} must be lowercase sha256")
    return normalized


def execution_payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json(payload, "payload"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AIExecutionRequest:
    operation_id: str
    execution_id: str
    objective: str
    context_policy: Mapping[str, Any]
    tool_policy: Mapping[str, Any]
    resource_budget: Mapping[str, Any]
    stop_policy: Mapping[str, Any]
    created_at: datetime
    checkpoint_ref: str | None = None
    schema_version: int = AI_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id", maximum=192)
        _text(self.execution_id, "execution_id", maximum=192)
        _text(self.objective, "objective")
        for name in ("context_policy", "tool_policy", "resource_budget", "stop_policy"):
            object.__setattr__(self, name, _json(getattr(self, name), name))
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        object.__setattr__(
            self, "checkpoint_ref", _optional_text(self.checkpoint_ref, "checkpoint_ref")
        )
        if self.schema_version != AI_EXECUTION_SCHEMA_VERSION:
            raise AIExecutionContractError("unsupported AI execution schema version")

    @property
    def identity_digest(self) -> str:
        return execution_payload_digest(
            {
                "operation_id": self.operation_id,
                "execution_id": self.execution_id,
                "objective": self.objective,
                "context_policy": dict(self.context_policy),
                "tool_policy": dict(self.tool_policy),
                "resource_budget": dict(self.resource_budget),
                "stop_policy": dict(self.stop_policy),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "objective": self.objective,
            "context_policy": dict(self.context_policy),
            "tool_policy": dict(self.tool_policy),
            "resource_budget": dict(self.resource_budget),
            "stop_policy": dict(self.stop_policy),
            "checkpoint_ref": self.checkpoint_ref,
            "created_at": self.created_at.isoformat(),
            "identity_digest": self.identity_digest,
        }


@dataclass(frozen=True, slots=True)
class AIExecution:
    request: AIExecutionRequest
    state: ExecutionState = ExecutionState.CREATED
    version: int = 1
    latest_turn_index: int = -1
    checkpoint_version: int = 0
    cancellation_requested: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = AI_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.request, AIExecutionRequest):
            raise AIExecutionContractError("request must be AIExecutionRequest")
        try:
            object.__setattr__(self, "state", ExecutionState(self.state))
        except ValueError as exc:
            raise AIExecutionContractError("execution state is invalid") from exc
        for name, minimum in (
            ("version", 1),
            ("latest_turn_index", -1),
            ("checkpoint_version", 0),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise AIExecutionContractError(f"{name} is invalid")
        if not isinstance(self.cancellation_requested, bool):
            raise AIExecutionContractError("cancellation_requested must be boolean")
        object.__setattr__(self, "updated_at", _aware(self.updated_at, "updated_at"))

    @property
    def operation_id(self) -> str:
        return self.request.operation_id

    @property
    def execution_id(self) -> str:
        return self.request.execution_id

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_EXECUTION_STATES

    def transition(
        self,
        target: ExecutionState | str,
        *,
        now: datetime | None = None,
    ) -> "AIExecution":
        try:
            target_state = ExecutionState(target)
        except ValueError as exc:
            raise AIExecutionContractError("unknown target execution state") from exc
        if target_state not in _ALLOWED_EXECUTION_TRANSITIONS[self.state]:
            raise AIExecutionContractError(
                f"illegal execution transition: {self.state.value} -> {target_state.value}"
            )
        return replace(
            self,
            state=target_state,
            version=self.version + 1,
            updated_at=_aware(now or datetime.now(timezone.utc), "now"),
        )


@dataclass(frozen=True, slots=True)
class AgentTurn:
    operation_id: str
    execution_id: str
    turn_id: str
    turn_index: int
    phase: ExecutionState
    context_digest: str
    checkpoint_ref: str
    status: str
    usage_delta: Mapping[str, Any] = field(default_factory=dict)
    parent_turn_id: str | None = None
    route_decision_id: str | None = None
    provider_request_id: str | None = None
    provider_response_id: str | None = None
    tool_receipt_ids: tuple[str, ...] = ()
    verification_receipt_id: str | None = None
    schema_version: int = AI_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("operation_id", "execution_id", "turn_id", "checkpoint_ref", "status"):
            _text(getattr(self, name), name, maximum=2048)
        if isinstance(self.turn_index, bool) or not isinstance(self.turn_index, int) or self.turn_index < 0:
            raise AIExecutionContractError("turn_index must be a non-negative integer")
        try:
            object.__setattr__(self, "phase", ExecutionState(self.phase))
        except ValueError as exc:
            raise AIExecutionContractError("turn phase is invalid") from exc
        object.__setattr__(self, "context_digest", _digest(self.context_digest, "context_digest"))
        for name in (
            "parent_turn_id",
            "route_decision_id",
            "provider_request_id",
            "provider_response_id",
            "verification_receipt_id",
        ):
            object.__setattr__(
                self, name, _optional_text(getattr(self, name), name)
            )
        if self.turn_index == 0 and self.parent_turn_id is not None:
            raise AIExecutionContractError("root turn cannot have parent_turn_id")
        if self.turn_index > 0 and self.parent_turn_id is None:
            raise AIExecutionContractError("non-root turn requires parent_turn_id")
        object.__setattr__(
            self,
            "tool_receipt_ids",
            _refs(self.tool_receipt_ids, "tool_receipt_ids", maximum=1024),
        )
        object.__setattr__(self, "usage_delta", _json(self.usage_delta, "usage_delta"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "parent_turn_id": self.parent_turn_id,
            "turn_index": self.turn_index,
            "phase": self.phase.value,
            "context_digest": self.context_digest,
            "route_decision_id": self.route_decision_id,
            "provider_request_id": self.provider_request_id,
            "provider_response_id": self.provider_response_id,
            "tool_receipt_ids": list(self.tool_receipt_ids),
            "verification_receipt_id": self.verification_receipt_id,
            "usage_delta": dict(self.usage_delta),
            "checkpoint_ref": self.checkpoint_ref,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ExecutionCheckpoint:
    operation_id: str
    execution_id: str
    checkpoint_version: int
    execution_version: int
    state: ExecutionState
    latest_turn_index: int
    payload: Mapping[str, Any]
    created_at: datetime
    payload_digest: str | None = None
    schema_version: int = AI_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id", maximum=192)
        _text(self.execution_id, "execution_id", maximum=192)
        for name, minimum in (
            ("checkpoint_version", 1),
            ("execution_version", 1),
            ("latest_turn_index", -1),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise AIExecutionContractError(f"{name} is invalid")
        try:
            object.__setattr__(self, "state", ExecutionState(self.state))
        except ValueError as exc:
            raise AIExecutionContractError("checkpoint state is invalid") from exc
        payload = _json(self.payload, "payload")
        object.__setattr__(self, "payload", payload)
        digest = execution_payload_digest(payload)
        if self.payload_digest is not None and self.payload_digest != digest:
            raise AIExecutionContractError("checkpoint payload_digest mismatch")
        object.__setattr__(self, "payload_digest", digest)
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))

    @property
    def checkpoint_ref(self) -> str:
        return f"execution-checkpoint:{self.execution_id}:{self.checkpoint_version}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "checkpoint_version": self.checkpoint_version,
            "execution_version": self.execution_version,
            "state": self.state.value,
            "latest_turn_index": self.latest_turn_index,
            "payload": dict(self.payload),
            "payload_digest": self.payload_digest,
            "checkpoint_ref": self.checkpoint_ref,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AIExecutionResult:
    operation_id: str
    execution_id: str
    status: str
    usage: Mapping[str, Any]
    completed_at: datetime
    final_output: str | None = None
    verification: str | None = None
    verification_receipt: Mapping[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()
    route_receipts: tuple[str, ...] = ()
    provider_receipts: tuple[str, ...] = ()
    tool_receipts: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    stream_terminal_event: str | None = None
    schema_version: int = AI_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id", maximum=192)
        _text(self.execution_id, "execution_id", maximum=192)
        status = _text(self.status, "status", maximum=128)
        if status not in {"completed", "degraded", "failed", "cancelled"}:
            raise AIExecutionContractError("result status is invalid")
        if status == "completed" and self.final_output is None:
            raise AIExecutionContractError("completed result requires final_output")
        for name in ("final_output", "verification", "stream_terminal_event"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if self.verification_receipt is not None:
            object.__setattr__(
                self,
                "verification_receipt",
                _json(self.verification_receipt, "verification_receipt"),
            )
        for name, maximum in (
            ("evidence_refs", 4096),
            ("route_receipts", 256),
            ("provider_receipts", 256),
            ("tool_receipts", 2048),
            ("memory_refs", 1024),
            ("artifact_refs", 1024),
        ):
            object.__setattr__(
                self, name, _refs(getattr(self, name), name, maximum=maximum)
            )
        object.__setattr__(self, "usage", _json(self.usage, "usage"))
        object.__setattr__(self, "completed_at", _aware(self.completed_at, "completed_at"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "status": self.status,
            "final_output": self.final_output,
            "verification": self.verification,
            "verification_receipt": (
                None
                if self.verification_receipt is None
                else dict(self.verification_receipt)
            ),
            "evidence_refs": list(self.evidence_refs),
            "route_receipts": list(self.route_receipts),
            "provider_receipts": list(self.provider_receipts),
            "tool_receipts": list(self.tool_receipts),
            "memory_refs": list(self.memory_refs),
            "artifact_refs": list(self.artifact_refs),
            "usage": dict(self.usage),
            "stream_terminal_event": self.stream_terminal_event,
            "completed_at": self.completed_at.isoformat(),
        }


__all__ = [
    "AI_EXECUTION_SCHEMA_VERSION",
    "AIExecution",
    "AIExecutionContractError",
    "AIExecutionRequest",
    "AIExecutionResult",
    "AgentTurn",
    "ExecutionCheckpoint",
    "ExecutionState",
    "TERMINAL_EXECUTION_STATES",
    "execution_payload_digest",
]
