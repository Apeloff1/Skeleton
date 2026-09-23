"""Canonical engine/application boundary contracts.

The backend may delegate an authenticated actor's authority to the Skeleton
engine, but delegation cannot widen tenant, capability, budget, or scopes.
Authority is bound to the exact operation/execution command by deterministic
digests; untrusted client transcript material is not accepted as state
authority at this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    ExecutionState,
)
from skeleton.contracts.operation import (
    OperationEnvelope,
    OperationState,
)


ENGINE_BOUNDARY_SCHEMA_VERSION = 1
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_AUTHORITY_KEYS = frozenset(
    {
        "conversation_history",
        "history",
        "messages",
        "transcript",
        "full_transcript",
        "client_transcript",
    }
)


class EngineBoundaryContractError(ValueError):
    """An engine-boundary command or authority contract is malformed."""


def _text(
    value: object,
    field_name: str,
    *,
    maximum: int = 2048,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EngineBoundaryContractError(
            f"{field_name} must be non-empty text"
        )
    normalized = value.strip()
    if normalized != value:
        raise EngineBoundaryContractError(
            f"{field_name} must be normalized"
        )
    if len(normalized) > maximum:
        raise EngineBoundaryContractError(
            f"{field_name} exceeds maximum length"
        )
    return normalized


def _aware(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise EngineBoundaryContractError(
            f"{field_name} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _digest(value: object, field_name: str) -> str:
    raw = _text(value, field_name, maximum=64)
    if _DIGEST.fullmatch(raw) is None:
        raise EngineBoundaryContractError(
            f"{field_name} must be lowercase sha256"
        )
    return raw


def _json_object(
    value: object,
    field_name: str,
    *,
    max_bytes: int = 512 * 1024,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineBoundaryContractError(
            f"{field_name} must be an object"
        )
    normalized = dict(value)
    try:
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EngineBoundaryContractError(
            f"{field_name} must be deterministic JSON"
        ) from exc
    if len(encoded) > max_bytes:
        raise EngineBoundaryContractError(
            f"{field_name} exceeds maximum size"
        )
    return normalized


def _refs(
    values: Iterable[str],
    field_name: str,
    *,
    maximum: int,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EngineBoundaryContractError(
            f"{field_name} must be an iterable"
        )
    result: list[str] = []
    for raw in values:
        item = _text(raw, field_name, maximum=2048)
        if item not in result:
            result.append(item)
        if len(result) > maximum:
            raise EngineBoundaryContractError(
                f"{field_name} exceeds maximum count"
            )
    return tuple(result)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_object(value, "digest payload"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reject_transcript_authority(value: object, *, path: str = "command") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if key in _FORBIDDEN_AUTHORITY_KEYS:
                raise EngineBoundaryContractError(
                    f"{path}.{key} cannot carry transcript authority"
                )
            _reject_transcript_authority(
                item,
                path=f"{path}.{key or '<empty>'}",
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_transcript_authority(
                item,
                path=f"{path}[{index}]",
            )


def _operation_from_dict(payload: Mapping[str, Any]) -> OperationEnvelope:
    try:
        return OperationEnvelope(
            operation_id=payload["operation_id"],
            tenant_id=payload["tenant_id"],
            actor_id=payload["actor_id"],
            capability=payload["capability"],
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            deadline=datetime.fromisoformat(str(payload["deadline"])),
            idempotency_key=payload["idempotency_key"],
            trace_id=payload["trace_id"],
            state=OperationState(payload.get("state", "created")),
        )
    except Exception as exc:
        raise EngineBoundaryContractError(
            "operation payload is invalid"
        ) from exc


def _execution_request_from_dict(
    payload: Mapping[str, Any],
) -> AIExecutionRequest:
    try:
        return AIExecutionRequest(
            operation_id=payload["operation_id"],
            execution_id=payload["execution_id"],
            objective=payload["objective"],
            context_policy=payload["context_policy"],
            tool_policy=payload["tool_policy"],
            resource_budget=payload["resource_budget"],
            stop_policy=payload["stop_policy"],
            checkpoint_ref=payload.get("checkpoint_ref"),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )
    except Exception as exc:
        raise EngineBoundaryContractError(
            "execution_request payload is invalid"
        ) from exc


@dataclass(frozen=True, slots=True)
class DelegatedAuthority:
    service_principal: str
    actor_id: str
    tenant_id: str
    scopes: tuple[str, ...]
    capability: str
    issued_at: datetime
    expires_at: datetime
    request_binding: str
    authority_digest: str | None = None
    schema_version: int = ENGINE_BOUNDARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "service_principal",
            "actor_id",
            "tenant_id",
            "capability",
        ):
            _text(getattr(self, name), name)
        scopes = _refs(self.scopes, "scopes", maximum=256)
        if not scopes:
            raise EngineBoundaryContractError(
                "delegated authority requires at least one scope"
            )
        object.__setattr__(self, "scopes", tuple(sorted(scopes)))
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= issued:
            raise EngineBoundaryContractError(
                "expires_at must be later than issued_at"
            )
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self,
            "request_binding",
            _digest(self.request_binding, "request_binding"),
        )
        computed = self.computed_authority_digest
        if (
            self.authority_digest is not None
            and _digest(
                self.authority_digest,
                "authority_digest",
            )
            != computed
        ):
            raise EngineBoundaryContractError(
                "authority_digest does not match delegated authority"
            )
        object.__setattr__(self, "authority_digest", computed)
        if self.schema_version != ENGINE_BOUNDARY_SCHEMA_VERSION:
            raise EngineBoundaryContractError(
                "unsupported engine boundary schema version"
            )

    @property
    def computed_authority_digest(self) -> str:
        return _canonical_digest(
            {
                "service_principal": self.service_principal,
                "actor_id": self.actor_id,
                "tenant_id": self.tenant_id,
                "scopes": list(self.scopes),
                "capability": self.capability,
                "issued_at": self.issued_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
                "request_binding": self.request_binding,
            }
        )

    def expired(self, *, now: datetime | None = None) -> bool:
        instant = _aware(
            now or datetime.now(timezone.utc),
            "now",
        )
        return instant >= self.expires_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "service_principal": self.service_principal,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "scopes": list(self.scopes),
            "capability": self.capability,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "request_binding": self.request_binding,
            "authority_digest": self.authority_digest,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "DelegatedAuthority":
        try:
            return cls(
                service_principal=payload["service_principal"],
                actor_id=payload["actor_id"],
                tenant_id=payload["tenant_id"],
                scopes=tuple(payload["scopes"]),
                capability=payload["capability"],
                issued_at=datetime.fromisoformat(
                    str(payload["issued_at"])
                ),
                expires_at=datetime.fromisoformat(
                    str(payload["expires_at"])
                ),
                request_binding=payload["request_binding"],
                authority_digest=payload.get("authority_digest"),
                schema_version=int(
                    payload.get(
                        "schema_version",
                        ENGINE_BOUNDARY_SCHEMA_VERSION,
                    )
                ),
            )
        except EngineBoundaryContractError:
            raise
        except Exception as exc:
            raise EngineBoundaryContractError(
                "delegated_authority payload is invalid"
            ) from exc


def engine_request_binding(
    operation: OperationEnvelope,
    execution_request: AIExecutionRequest,
    *,
    context_seed_refs: Iterable[str] = (),
    resource_budget: Mapping[str, Any] | None = None,
    stream_preferences: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(operation, OperationEnvelope):
        raise TypeError("operation must be OperationEnvelope")
    if not isinstance(execution_request, AIExecutionRequest):
        raise TypeError(
            "execution_request must be AIExecutionRequest"
        )
    seeds = _refs(
        context_seed_refs,
        "context_seed_refs",
        maximum=1024,
    )
    budget = _json_object(
        (
            execution_request.resource_budget
            if resource_budget is None
            else resource_budget
        ),
        "resource_budget",
    )
    stream = _json_object(
        stream_preferences or {},
        "stream_preferences",
    )
    return _canonical_digest(
        {
            "operation_identity_digest": operation.identity_digest,
            "operation_id": operation.operation_id,
            "trace_id": operation.trace_id,
            "execution_identity_digest": execution_request.identity_digest,
            "execution_id": execution_request.execution_id,
            "context_seed_refs": list(seeds),
            "resource_budget": budget,
            "stream_preferences": stream,
        }
    )


@dataclass(frozen=True, slots=True)
class EngineExecutionCommand:
    operation: OperationEnvelope
    execution_request: AIExecutionRequest
    delegated_authority: DelegatedAuthority
    context_seed_refs: tuple[str, ...] = ()
    resource_budget: Mapping[str, Any] = field(default_factory=dict)
    stream_preferences: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = ENGINE_BOUNDARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationEnvelope):
            raise EngineBoundaryContractError(
                "operation must be OperationEnvelope"
            )
        if not isinstance(
            self.execution_request,
            AIExecutionRequest,
        ):
            raise EngineBoundaryContractError(
                "execution_request must be AIExecutionRequest"
            )
        if not isinstance(
            self.delegated_authority,
            DelegatedAuthority,
        ):
            raise EngineBoundaryContractError(
                "delegated_authority must be DelegatedAuthority"
            )
        if (
            self.operation.operation_id
            != self.execution_request.operation_id
        ):
            raise EngineBoundaryContractError(
                "operation_id does not match execution_request"
            )
        authority = self.delegated_authority
        if authority.actor_id != self.operation.actor_id:
            raise EngineBoundaryContractError(
                "delegated actor does not match operation"
            )
        if authority.tenant_id != self.operation.tenant_id:
            raise EngineBoundaryContractError(
                "delegated tenant does not match operation"
            )
        if authority.capability != self.operation.capability:
            raise EngineBoundaryContractError(
                "delegated capability does not match operation"
            )

        seeds = _refs(
            self.context_seed_refs,
            "context_seed_refs",
            maximum=1024,
        )
        object.__setattr__(
            self,
            "context_seed_refs",
            seeds,
        )
        budget = _json_object(
            self.resource_budget,
            "resource_budget",
        )
        if not budget:
            budget = dict(
                self.execution_request.resource_budget
            )
        if budget != dict(
            self.execution_request.resource_budget
        ):
            raise EngineBoundaryContractError(
                "command resource_budget must exactly match execution request"
            )
        object.__setattr__(
            self,
            "resource_budget",
            budget,
        )
        stream = _json_object(
            self.stream_preferences,
            "stream_preferences",
        )
        object.__setattr__(
            self,
            "stream_preferences",
            stream,
        )

        for policy_name in ("context_policy", "tool_policy"):
            policy = getattr(
                self.execution_request,
                policy_name,
            )
            tenant = policy.get("tenant_id")
            if (
                tenant is not None
                and str(tenant).strip()
                != self.operation.tenant_id
            ):
                raise EngineBoundaryContractError(
                    f"{policy_name} tenant does not match operation"
                )
            _reject_transcript_authority(
                policy,
                path=policy_name,
            )
        _reject_transcript_authority(
            stream,
            path="stream_preferences",
        )

        expected_binding = engine_request_binding(
            self.operation,
            self.execution_request,
            context_seed_refs=seeds,
            resource_budget=budget,
            stream_preferences=stream,
        )
        if authority.request_binding != expected_binding:
            raise EngineBoundaryContractError(
                "delegated authority is not bound to this execution command"
            )
        if (
            self.execution_request.created_at
            < self.operation.created_at
        ):
            raise EngineBoundaryContractError(
                "execution cannot predate operation"
            )
        deadline = self.execution_request.stop_policy.get(
            "deadline"
        )
        if deadline is not None:
            try:
                execution_deadline = datetime.fromisoformat(
                    str(deadline)
                ).astimezone(timezone.utc)
            except Exception as exc:
                raise EngineBoundaryContractError(
                    "execution stop deadline is invalid"
                ) from exc
            if execution_deadline > self.operation.deadline:
                raise EngineBoundaryContractError(
                    "execution deadline exceeds operation deadline"
                )
        if self.schema_version != ENGINE_BOUNDARY_SCHEMA_VERSION:
            raise EngineBoundaryContractError(
                "unsupported engine boundary schema version"
            )

    @property
    def idempotency_digest(self) -> str:
        return _canonical_digest(
            {
                "operation_identity_digest": self.operation.identity_digest,
                "execution_identity_digest": (
                    self.execution_request.identity_digest
                ),
                "request_binding": (
                    self.delegated_authority.request_binding
                ),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.as_dict(),
            "execution_request": (
                self.execution_request.as_dict()
            ),
            "delegated_authority": (
                self.delegated_authority.as_dict()
            ),
            "context_seed_refs": list(
                self.context_seed_refs
            ),
            "resource_budget": dict(
                self.resource_budget
            ),
            "stream_preferences": dict(
                self.stream_preferences
            ),
            "idempotency_digest": (
                self.idempotency_digest
            ),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "EngineExecutionCommand":
        try:
            operation_raw = payload["operation"]
            execution_raw = payload["execution_request"]
            authority_raw = payload["delegated_authority"]
            if not isinstance(operation_raw, Mapping):
                raise TypeError("operation")
            if not isinstance(execution_raw, Mapping):
                raise TypeError("execution_request")
            if not isinstance(authority_raw, Mapping):
                raise TypeError("delegated_authority")
            return cls(
                operation=_operation_from_dict(operation_raw),
                execution_request=_execution_request_from_dict(
                    execution_raw
                ),
                delegated_authority=(
                    DelegatedAuthority.from_dict(
                        authority_raw
                    )
                ),
                context_seed_refs=tuple(
                    payload.get(
                        "context_seed_refs",
                        (),
                    )
                ),
                resource_budget=dict(
                    payload.get(
                        "resource_budget",
                        {},
                    )
                ),
                stream_preferences=dict(
                    payload.get(
                        "stream_preferences",
                        {},
                    )
                ),
                schema_version=int(
                    payload.get(
                        "schema_version",
                        ENGINE_BOUNDARY_SCHEMA_VERSION,
                    )
                ),
            )
        except EngineBoundaryContractError:
            raise
        except Exception as exc:
            raise EngineBoundaryContractError(
                "engine execution command payload is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class EngineExecutionAck:
    operation_id: str
    execution_id: str
    state: OperationState
    accepted_at: datetime
    idempotency_digest: str
    status_ref: str
    events_ref: str
    trace_id: str
    schema_version: int = ENGINE_BOUNDARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "execution_id",
            "status_ref",
            "events_ref",
            "trace_id",
        ):
            _text(getattr(self, name), name)
        try:
            object.__setattr__(
                self,
                "state",
                OperationState(self.state),
            )
        except ValueError as exc:
            raise EngineBoundaryContractError(
                "ack state is invalid"
            ) from exc
        object.__setattr__(
            self,
            "accepted_at",
            _aware(self.accepted_at, "accepted_at"),
        )
        object.__setattr__(
            self,
            "idempotency_digest",
            _digest(
                self.idempotency_digest,
                "idempotency_digest",
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "state": self.state.value,
            "accepted_at": self.accepted_at.isoformat(),
            "idempotency_digest": self.idempotency_digest,
            "status_ref": self.status_ref,
            "events_ref": self.events_ref,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True, slots=True)
class EngineExecutionStatus:
    operation_id: str
    execution_id: str
    operation_state: OperationState
    execution_state: ExecutionState
    latest_checkpoint_version: int
    updated_at: datetime
    result_ref: str | None = None
    failure_code: str | None = None
    schema_version: int = ENGINE_BOUNDARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id")
        _text(self.execution_id, "execution_id")
        try:
            object.__setattr__(
                self,
                "operation_state",
                OperationState(self.operation_state),
            )
            object.__setattr__(
                self,
                "execution_state",
                ExecutionState(self.execution_state),
            )
        except ValueError as exc:
            raise EngineBoundaryContractError(
                "status state is invalid"
            ) from exc
        if (
            isinstance(self.latest_checkpoint_version, bool)
            or not isinstance(
                self.latest_checkpoint_version,
                int,
            )
            or self.latest_checkpoint_version < 0
        ):
            raise EngineBoundaryContractError(
                "latest_checkpoint_version is invalid"
            )
        object.__setattr__(
            self,
            "updated_at",
            _aware(self.updated_at, "updated_at"),
        )
        if self.result_ref is not None:
            object.__setattr__(
                self,
                "result_ref",
                _text(
                    self.result_ref,
                    "result_ref",
                ),
            )
        if self.failure_code is not None:
            object.__setattr__(
                self,
                "failure_code",
                _text(
                    self.failure_code,
                    "failure_code",
                    maximum=128,
                ),
            )
        if (
            self.operation_state
            is OperationState.COMPLETED
            and self.result_ref is None
        ):
            raise EngineBoundaryContractError(
                "completed status requires result_ref"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "operation_state": self.operation_state.value,
            "execution_state": self.execution_state.value,
            "latest_checkpoint_version": (
                self.latest_checkpoint_version
            ),
            "result_ref": self.result_ref,
            "failure_code": self.failure_code,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class EngineCancelCommand:
    operation_id: str
    actor_id: str
    tenant_id: str
    reason: str
    requested_at: datetime
    idempotency_key: str
    schema_version: int = ENGINE_BOUNDARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "actor_id",
            "tenant_id",
            "reason",
            "idempotency_key",
        ):
            _text(
                getattr(self, name),
                name,
                maximum=(
                    2048
                    if name == "reason"
                    else 256
                ),
            )
        object.__setattr__(
            self,
            "requested_at",
            _aware(self.requested_at, "requested_at"),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "EngineCancelCommand":
        try:
            return cls(
                operation_id=payload["operation_id"],
                actor_id=payload["actor_id"],
                tenant_id=payload["tenant_id"],
                reason=payload["reason"],
                requested_at=datetime.fromisoformat(
                    str(payload["requested_at"])
                ),
                idempotency_key=payload[
                    "idempotency_key"
                ],
                schema_version=int(
                    payload.get(
                        "schema_version",
                        ENGINE_BOUNDARY_SCHEMA_VERSION,
                    )
                ),
            )
        except EngineBoundaryContractError:
            raise
        except Exception as exc:
            raise EngineBoundaryContractError(
                "engine cancel command payload is invalid"
            ) from exc


__all__ = [
    "DelegatedAuthority",
    "ENGINE_BOUNDARY_SCHEMA_VERSION",
    "EngineBoundaryContractError",
    "EngineCancelCommand",
    "EngineExecutionAck",
    "EngineExecutionCommand",
    "EngineExecutionStatus",
    "engine_request_binding",
]
