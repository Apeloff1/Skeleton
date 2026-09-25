"""Authenticated engine execution service over durable cognitive state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
)
from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    ExecutionState,
)
from skeleton.contracts.operation import (
    OperationEnvelope,
    OperationState,
)
from skeleton.provider_contract import ProviderToolDefinition
from skeleton.skills.tool_contract import ToolExecutionRequest, approval_ref_for_request
from skeleton.persistence.execution_repository import (
    ExecutionRepositoryConflict,
    ExecutionRepositoryError,
    SQLiteExecutionRepository,
)


class EngineServiceError(RuntimeError):
    """Base engine service failure."""


class EngineSubmissionConflict(EngineServiceError):
    """Idempotent submission identity was reused with different content."""


def _aware(raw: object, field: str) -> datetime:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise EngineServiceError(f"{field} is invalid") from exc
    else:
        raise EngineServiceError(f"{field} is invalid")
    if value.tzinfo is None or value.utcoffset() is None:
        raise EngineServiceError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EngineServiceError(f"{field} must be an object")
    result = dict(value)
    try:
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EngineServiceError(f"{field} must be deterministic JSON") from exc
    return result


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _operation_from_dict(payload: Mapping[str, Any]) -> OperationEnvelope:
    data = _json_object(payload, "operation")
    try:
        return OperationEnvelope(
            operation_id=str(data["operation_id"]),
            tenant_id=str(data["tenant_id"]),
            actor_id=str(data["actor_id"]),
            capability=str(data["capability"]),
            created_at=_aware(data["created_at"], "operation.created_at"),
            deadline=_aware(data["deadline"], "operation.deadline"),
            idempotency_key=str(data["idempotency_key"]),
            trace_id=str(data["trace_id"]),
            state=OperationState(str(data.get("state", "created"))),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise EngineServiceError("operation is malformed") from exc


def _execution_request_from_dict(payload: Mapping[str, Any]) -> AIExecutionRequest:
    data = _json_object(payload, "execution_request")
    try:
        return AIExecutionRequest(
            operation_id=str(data["operation_id"]),
            execution_id=str(data["execution_id"]),
            objective=str(data["objective"]),
            context_policy=_json_object(data["context_policy"], "context_policy"),
            tool_policy=_json_object(data["tool_policy"], "tool_policy"),
            resource_budget=_json_object(data["resource_budget"], "resource_budget"),
            stop_policy=_json_object(data["stop_policy"], "stop_policy"),
            checkpoint_ref=(
                None
                if data.get("checkpoint_ref") is None
                else str(data["checkpoint_ref"])
            ),
            created_at=_aware(data["created_at"], "execution_request.created_at"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise EngineServiceError("execution_request is malformed") from exc


@dataclass(frozen=True, slots=True)
class EngineContextHandoff:
    """Digest-bound projection of one server-compiled context envelope."""

    operation_id: str
    execution_id: str
    turn_id: str
    tenant_id: str
    context_id: str
    context_digest: str
    compiler_version: str
    source_snapshot: tuple[tuple[str, str], ...]
    data_class: str
    instructions: str
    prompt: str
    purpose: str = "model-inference"
    history: tuple[tuple[str, str], ...] = ()
    tools: tuple[ProviderToolDefinition, ...] = ()
    model: str | None = None
    structured_output_schema: Mapping[str, Any] | None = None
    tool_choice: str = "auto"
    specific_tool_id: str | None = None
    estimated_cost_usd: float = 0.0
    handoff_digest: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "execution_id",
            "turn_id",
            "tenant_id",
            "context_id",
            "compiler_version",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise EngineServiceError(f"{name} is required")
            object.__setattr__(self, name, value)
        digest = str(self.context_digest).strip()
        if (
            len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise EngineServiceError(
                "compiled context digest must be lowercase sha256"
            )
        object.__setattr__(self, "context_digest", digest)
        data_class = str(self.data_class).strip().lower()
        if data_class not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise EngineServiceError("compiled context data_class is invalid")
        object.__setattr__(self, "data_class", data_class)
        purpose = str(self.purpose).strip()
        if not purpose or len(purpose) > 256:
            raise EngineServiceError(
                "compiled context purpose is invalid"
            )
        object.__setattr__(self, "purpose", purpose)
        instructions = str(self.instructions)
        prompt = str(self.prompt)
        if not instructions.strip() or not prompt.strip():
            raise EngineServiceError(
                "compiled context handoff requires instructions and prompt"
            )
        if instructions.strip() != instructions or prompt.strip() != prompt:
            raise EngineServiceError(
                "compiled context instructions/prompt must be normalized"
            )
        if len(instructions) > 1_000_000 or len(prompt) > 1_000_000:
            raise EngineServiceError("compiled context handoff is too large")

        snapshot: list[tuple[str, str]] = []
        for item in self.source_snapshot:
            if not isinstance(item, tuple) or len(item) != 2:
                raise EngineServiceError(
                    "compiled context source_snapshot entries must be pairs"
                )
            segment_id = str(item[0]).strip()
            segment_digest = str(item[1]).strip()
            if (
                not segment_id
                or len(segment_digest) != 64
                or any(
                    ch not in "0123456789abcdef"
                    for ch in segment_digest
                )
            ):
                raise EngineServiceError(
                    "compiled context source_snapshot entry is invalid"
                )
            snapshot.append((segment_id, segment_digest))
        if len(snapshot) != len(set(segment_id for segment_id, _ in snapshot)):
            raise EngineServiceError(
                "compiled context source_snapshot contains duplicate segment"
            )
        object.__setattr__(self, "source_snapshot", tuple(snapshot))

        history: list[tuple[str, str]] = []
        for item in self.history:
            if not isinstance(item, tuple) or len(item) != 2:
                raise EngineServiceError(
                    "compiled context history entries must be pairs"
                )
            role = str(item[0]).strip()
            content = str(item[1])
            if role not in {"user", "assistant"}:
                raise EngineServiceError(
                    "compiled context history role is invalid"
                )
            if not content.strip() or content.strip() != content:
                raise EngineServiceError(
                    "compiled context history content is invalid"
                )
            history.append((role, content))
            if len(history) > 1024:
                raise EngineServiceError(
                    "compiled context history exceeds maximum turns"
                )
        object.__setattr__(self, "history", tuple(history))

        tools: list[ProviderToolDefinition] = []
        seen_tools: set[str] = set()
        for tool in self.tools:
            if not isinstance(tool, ProviderToolDefinition):
                raise EngineServiceError(
                    "compiled context tools must be ProviderToolDefinition values"
                )
            if tool.tool_id in seen_tools:
                raise EngineServiceError(
                    "compiled context tools contain duplicate tool id"
                )
            seen_tools.add(tool.tool_id)
            tools.append(tool)
        object.__setattr__(self, "tools", tuple(tools))

        if self.model is not None:
            model = str(self.model).strip()
            if not model or len(model) > 256:
                raise EngineServiceError(
                    "compiled context provider model is invalid"
                )
            object.__setattr__(self, "model", model)
        if self.structured_output_schema is not None:
            object.__setattr__(
                self,
                "structured_output_schema",
                _json_object(
                    self.structured_output_schema,
                    "structured_output_schema",
                ),
            )
        choice = str(self.tool_choice).strip().lower()
        if choice not in {"none", "auto", "required", "specific"}:
            raise EngineServiceError(
                "compiled context tool_choice is invalid"
            )
        object.__setattr__(self, "tool_choice", choice)
        if self.specific_tool_id is not None:
            specific = str(self.specific_tool_id).strip()
            if not specific:
                raise EngineServiceError(
                    "compiled context specific_tool_id is invalid"
                )
            object.__setattr__(self, "specific_tool_id", specific)
        if choice == "specific":
            if self.specific_tool_id is None:
                raise EngineServiceError(
                    "specific tool choice requires specific_tool_id"
                )
            if self.specific_tool_id not in {
                tool.tool_id for tool in tools
            }:
                raise EngineServiceError(
                    "specific tool choice is not offered"
                )
        elif self.specific_tool_id is not None:
            raise EngineServiceError(
                "specific_tool_id requires tool_choice='specific'"
            )
        try:
            estimated = float(self.estimated_cost_usd)
        except (TypeError, ValueError) as exc:
            raise EngineServiceError(
                "compiled context estimated_cost_usd is invalid"
            ) from exc
        if estimated < 0 or estimated != estimated:
            raise EngineServiceError(
                "compiled context estimated_cost_usd is invalid"
            )
        object.__setattr__(self, "estimated_cost_usd", estimated)

        expected = _digest(self._digest_payload())
        if self.handoff_digest is not None and self.handoff_digest != expected:
            raise EngineServiceError(
                "compiled context handoff_digest does not match payload"
            )
        object.__setattr__(self, "handoff_digest", expected)
        if self.schema_version != 1:
            raise EngineServiceError(
                "unsupported compiled context handoff schema version"
            )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "tenant_id": self.tenant_id,
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "compiler_version": self.compiler_version,
            "source_snapshot": [
                [segment_id, digest]
                for segment_id, digest in self.source_snapshot
            ],
            "data_class": self.data_class,
            "purpose": self.purpose,
            "instructions": self.instructions,
            "prompt": self.prompt,
            "history": [
                {"role": role, "content": content}
                for role, content in self.history
            ],
            "tools": [tool.as_dict() for tool in self.tools],
            "model": self.model,
            "structured_output_schema": (
                None
                if self.structured_output_schema is None
                else dict(self.structured_output_schema)
            ),
            "tool_choice": self.tool_choice,
            "specific_tool_id": self.specific_tool_id,
            "estimated_cost_usd": self.estimated_cost_usd,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            **self._digest_payload(),
            "handoff_digest": self.handoff_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineContextHandoff":
        data = _json_object(payload, "compiled_context")
        raw_snapshot = data.get("source_snapshot", [])
        raw_history = data.get("history", [])
        raw_tools = data.get("tools", [])
        if (
            not isinstance(raw_snapshot, list)
            or not isinstance(raw_history, list)
            or not isinstance(raw_tools, list)
        ):
            raise EngineServiceError(
                "compiled context arrays are malformed"
            )
        snapshot = tuple(
            (str(item[0]), str(item[1]))
            for item in raw_snapshot
            if isinstance(item, list) and len(item) == 2
        )
        if len(snapshot) != len(raw_snapshot):
            raise EngineServiceError(
                "compiled context source_snapshot is malformed"
            )
        history: list[tuple[str, str]] = []
        for item in raw_history:
            if not isinstance(item, Mapping):
                raise EngineServiceError(
                    "compiled context history is malformed"
                )
            history.append(
                (
                    str(item.get("role") or ""),
                    str(item.get("content") or ""),
                )
            )
        tools: list[ProviderToolDefinition] = []
        for item in raw_tools:
            if not isinstance(item, Mapping):
                raise EngineServiceError(
                    "compiled context tool definition is malformed"
                )
            tools.append(
                ProviderToolDefinition(
                    tool_id=str(item.get("tool_id") or ""),
                    description=str(item.get("description") or ""),
                    input_schema=_json_object(
                        item.get("input_schema"),
                        "compiled tool input_schema",
                    ),
                )
            )
        return cls(
            operation_id=str(data.get("operation_id") or ""),
            execution_id=str(data.get("execution_id") or ""),
            turn_id=str(data.get("turn_id") or ""),
            tenant_id=str(data.get("tenant_id") or ""),
            context_id=str(data.get("context_id") or ""),
            context_digest=str(data.get("context_digest") or ""),
            compiler_version=str(data.get("compiler_version") or ""),
            source_snapshot=snapshot,
            data_class=str(data.get("data_class") or ""),
            purpose=str(data.get("purpose") or "model-inference"),
            instructions=str(data.get("instructions") or ""),
            prompt=str(data.get("prompt") or ""),
            history=tuple(history),
            tools=tuple(tools),
            model=(
                None
                if data.get("model") is None
                else str(data["model"])
            ),
            structured_output_schema=(
                None
                if data.get("structured_output_schema") is None
                else _json_object(
                    data["structured_output_schema"],
                    "structured_output_schema",
                )
            ),
            tool_choice=str(data.get("tool_choice", "auto")),
            specific_tool_id=(
                None
                if data.get("specific_tool_id") is None
                else str(data["specific_tool_id"])
            ),
            estimated_cost_usd=float(
                data.get("estimated_cost_usd", 0.0)
            ),
            handoff_digest=(
                None
                if data.get("handoff_digest") is None
                else str(data["handoff_digest"])
            ),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass(frozen=True, slots=True)
class EngineExecutionCommand:
    operation: OperationEnvelope
    execution_request: AIExecutionRequest
    delegated_authority: DelegatedAuthority
    compiled_context: EngineContextHandoff
    context_seed_refs: tuple[str, ...]
    resource_budget: Mapping[str, Any]
    stream_preferences: Mapping[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationEnvelope):
            raise EngineServiceError("operation must be OperationEnvelope")
        if not isinstance(self.execution_request, AIExecutionRequest):
            raise EngineServiceError(
                "execution_request must be AIExecutionRequest"
            )
        if not isinstance(self.delegated_authority, DelegatedAuthority):
            raise EngineServiceError(
                "delegated_authority must be DelegatedAuthority"
            )
        if not isinstance(self.compiled_context, EngineContextHandoff):
            raise EngineServiceError(
                "compiled_context must be EngineContextHandoff"
            )
        handoff = self.compiled_context
        if handoff.operation_id != self.operation.operation_id:
            raise EngineServiceError(
                "compiled context operation_id mismatch"
            )
        if handoff.execution_id != self.execution_request.execution_id:
            raise EngineServiceError(
                "compiled context execution_id mismatch"
            )
        if handoff.tenant_id != self.operation.tenant_id:
            raise EngineServiceError(
                "compiled context tenant_id mismatch"
            )
        context_policy = dict(self.execution_request.context_policy)
        if context_policy.get("context_id") != handoff.context_id:
            raise EngineServiceError(
                "compiled context id does not match execution policy"
            )
        if context_policy.get("context_digest") != handoff.context_digest:
            raise EngineServiceError(
                "compiled context digest does not match execution policy"
            )
        if context_policy.get("handoff_digest") != handoff.handoff_digest:
            raise EngineServiceError(
                "compiled context handoff is not bound to execution identity"
            )
        expected_snapshot = [
            [segment_id, digest]
            for segment_id, digest in handoff.source_snapshot
        ]
        if context_policy.get("source_snapshot") != expected_snapshot:
            raise EngineServiceError(
                "compiled context source snapshot mismatch"
            )
        refs: list[str] = []
        for raw in self.context_seed_refs:
            if not isinstance(raw, str) or not raw.strip():
                raise EngineServiceError("context_seed_refs must contain text")
            ref = raw.strip()
            if ref != raw or len(ref) > 2048:
                raise EngineServiceError("context seed ref is invalid")
            if ref not in refs:
                refs.append(ref)
            if len(refs) > 1024:
                raise EngineServiceError("too many context seed refs")
        object.__setattr__(self, "context_seed_refs", tuple(refs))
        budget = _json_object(self.resource_budget, "resource_budget")
        preferences = _json_object(
            self.stream_preferences,
            "stream_preferences",
        )
        object.__setattr__(self, "resource_budget", budget)
        object.__setattr__(self, "stream_preferences", preferences)
        if budget != dict(self.execution_request.resource_budget):
            raise EngineServiceError(
                "command resource_budget must equal execution request budget"
            )
        if self.schema_version != 1:
            raise EngineServiceError(
                "unsupported engine execution command schema version"
            )

    @property
    def command_digest(self) -> str:
        """Full audit digest including temporal authority material."""

        return _digest(self.as_dict(include_authority_digest=True))

    @property
    def submission_digest(self) -> str:
        """Stable semantic digest used for idempotent submission replay.

        Delegated authority timestamps, operation timestamps, trace timestamps,
        and other freshness material are intentionally excluded. The service
        validates the fresh authority before replay lookup; this digest decides
        only whether the requested work is semantically the same work.
        """

        return _digest(
            {
                "schema_version": self.schema_version,
                "operation_id": self.operation.operation_id,
                "operation_identity_digest": self.operation.identity_digest,
                "execution_id": self.execution_request.execution_id,
                "execution_identity_digest": (
                    self.execution_request.identity_digest
                ),
                "compiled_context_handoff_digest": (
                    self.compiled_context.handoff_digest
                ),
                "context_seed_refs": list(self.context_seed_refs),
                "resource_budget": dict(self.resource_budget),
                "stream_preferences": dict(self.stream_preferences),
            }
        )

    def as_dict(self, *, include_authority_digest: bool = True) -> dict[str, Any]:
        authority = self.delegated_authority.as_dict()
        if not include_authority_digest:
            authority = dict(authority)
            authority.pop("authority_digest", None)
        return {
            "schema_version": self.schema_version,
            "operation": self.operation.as_dict(),
            "execution_request": self.execution_request.as_dict(),
            "delegated_authority": authority,
            "compiled_context": self.compiled_context.as_dict(),
            "context_seed_refs": list(self.context_seed_refs),
            "resource_budget": dict(self.resource_budget),
            "stream_preferences": dict(self.stream_preferences),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EngineExecutionCommand":
        data = _json_object(payload, "engine execution command")
        allowed = {
            "schema_version",
            "operation",
            "execution_request",
            "delegated_authority",
            "compiled_context",
            "context_seed_refs",
            "resource_budget",
            "stream_preferences",
        }
        extras = set(data) - allowed
        if extras:
            raise EngineServiceError(
                "engine command contains unsupported fields: "
                + ", ".join(sorted(extras))
            )
        for forbidden in (
            "conversation_history",
            "messages",
            "history",
            "transcript",
        ):
            if forbidden in data:
                raise EngineServiceError(
                    "engine command cannot carry client transcript authority"
                )
        refs = data.get("context_seed_refs", [])
        if not isinstance(refs, list):
            raise EngineServiceError("context_seed_refs must be a list")
        return cls(
            operation=_operation_from_dict(
                _json_object(data.get("operation"), "operation")
            ),
            execution_request=_execution_request_from_dict(
                _json_object(
                    data.get("execution_request"),
                    "execution_request",
                )
            ),
            delegated_authority=DelegatedAuthority.from_dict(
                _json_object(
                    data.get("delegated_authority"),
                    "delegated_authority",
                )
            ),
            compiled_context=EngineContextHandoff.from_dict(
                _json_object(
                    data.get("compiled_context"),
                    "compiled_context",
                )
            ),
            context_seed_refs=tuple(refs),
            resource_budget=_json_object(
                data.get("resource_budget"),
                "resource_budget",
            ),
            stream_preferences=_json_object(
                data.get("stream_preferences", {}),
                "stream_preferences",
            ),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass(frozen=True, slots=True)
class EngineExecutionAck:
    operation_id: str
    execution_id: str
    state: str
    accepted_at: datetime
    idempotency_digest: str
    status_ref: str
    events_ref: str
    trace_id: str
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "state": self.state,
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
    operation_state: str
    execution_state: str
    latest_checkpoint_version: int
    result_ref: str | None
    failure_code: str | None
    updated_at: datetime
    cancellation_requested: bool = False
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "operation_state": self.operation_state,
            "execution_state": self.execution_state,
            "latest_checkpoint_version": self.latest_checkpoint_version,
            "result_ref": self.result_ref,
            "failure_code": self.failure_code,
            "updated_at": self.updated_at.isoformat(),
            "cancellation_requested": self.cancellation_requested,
        }


@dataclass(frozen=True, slots=True)
class EngineToolApproval:
    approval_id: str
    execution_id: str
    call_id: str
    tool_id: str
    arguments_digest: str
    actor_id: str
    tenant_id: str
    idempotency_key: str
    bound_approval_ref: str
    issued_at: datetime
    expires_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in (
            "approval_id",
            "execution_id",
            "call_id",
            "tool_id",
            "actor_id",
            "tenant_id",
            "idempotency_key",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise EngineServiceError(f"{name} is required")
            if len(value) > 2048:
                raise EngineServiceError(f"{name} exceeds maximum length")
            object.__setattr__(self, name, value)
        digest = str(self.arguments_digest).strip()
        if (
            len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise EngineServiceError(
                "arguments_digest must be lowercase sha256"
            )
        object.__setattr__(self, "arguments_digest", digest)
        approval_ref = str(self.bound_approval_ref).strip()
        if not approval_ref.startswith("approval:") or len(approval_ref) > 1024:
            raise EngineServiceError(
                "bound_approval_ref must be a request-bound approval capability"
            )
        object.__setattr__(self, "bound_approval_ref", approval_ref)
        issued = _aware(self.issued_at, "approval.issued_at")
        expires = _aware(self.expires_at, "approval.expires_at")
        if expires <= issued:
            raise EngineServiceError(
                "approval expires_at must be later than issued_at"
            )
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if self.schema_version != 1:
            raise EngineServiceError(
                "unsupported engine tool approval schema version"
            )

    @property
    def approval_ref(self) -> str:
        return self.bound_approval_ref

    def expired(self, *, now: datetime | None = None) -> bool:
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else _aware(now, "approval.now")
        )
        return instant >= self.expires_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "approval_id": self.approval_id,
            "approval_ref": self.approval_ref,
            "execution_id": self.execution_id,
            "call_id": self.call_id,
            "tool_id": self.tool_id,
            "arguments_digest": self.arguments_digest,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "idempotency_key": self.idempotency_key,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class _StoredSubmission:
    principal: str
    command: EngineExecutionCommand
    ack: EngineExecutionAck


class SQLiteEngineSubmissionStore:
    """Durable operation/idempotency -> canonical engine acknowledgement."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "engine_submission",
    ) -> None:
        self.namespace = str(namespace).strip()
        if not self.namespace:
            raise ValueError("namespace must not be empty")
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS engine_submission (
                    namespace TEXT NOT NULL,
                    service_principal TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    command_digest TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    ack_json TEXT NOT NULL,
                    accepted_at TEXT NOT NULL,
                    PRIMARY KEY(
                        namespace, service_principal, tenant_id,
                        operation_id, idempotency_key
                    ),
                    UNIQUE(namespace, execution_id)
                );

                CREATE TABLE IF NOT EXISTS engine_tool_approval (
                    namespace TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    call_id TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    arguments_digest TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    approval_ref TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, approval_id),
                    UNIQUE(
                        namespace, execution_id, call_id, idempotency_key
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_engine_tool_approval_active
                ON engine_tool_approval(
                    namespace, execution_id, call_id, expires_at
                );
                """
            )

    @staticmethod
    def _ack_from_dict(data: Mapping[str, Any]) -> EngineExecutionAck:
        return EngineExecutionAck(
            operation_id=str(data["operation_id"]),
            execution_id=str(data["execution_id"]),
            state=str(data["state"]),
            accepted_at=_aware(data["accepted_at"], "accepted_at"),
            idempotency_digest=str(data["idempotency_digest"]),
            status_ref=str(data["status_ref"]),
            events_ref=str(data["events_ref"]),
            trace_id=str(data["trace_id"]),
            schema_version=int(data.get("schema_version", 1)),
        )

    def get(
        self,
        *,
        service_principal: str,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> _StoredSubmission | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM engine_submission
                WHERE namespace = ?
                  AND service_principal = ?
                  AND tenant_id = ?
                  AND operation_id = ?
                  AND idempotency_key = ?
                """,
                (
                    self.namespace,
                    service_principal,
                    tenant_id,
                    operation_id,
                    idempotency_key,
                ),
            ).fetchone()
            if row is None:
                return None
            try:
                command_payload = json.loads(row["command_json"])
                ack_payload = json.loads(row["ack_json"])
            except json.JSONDecodeError as exc:
                raise EngineServiceError(
                    "stored engine submission is corrupt"
                ) from exc
            return _StoredSubmission(
                principal=row["service_principal"],
                command=EngineExecutionCommand.from_dict(command_payload),
                ack=self._ack_from_dict(ack_payload),
            )

    def get_by_execution_id(
        self,
        execution_id: str,
    ) -> _StoredSubmission | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT service_principal, tenant_id, operation_id, idempotency_key
                FROM engine_submission
                WHERE namespace = ? AND execution_id = ?
                """,
                (self.namespace, execution_id),
            ).fetchone()
        if row is None:
            return None
        return self.get(
            service_principal=row["service_principal"],
            tenant_id=row["tenant_id"],
            operation_id=row["operation_id"],
            idempotency_key=row["idempotency_key"],
        )

    def remember(
        self,
        *,
        service_principal: str,
        command: EngineExecutionCommand,
        ack: EngineExecutionAck,
    ) -> EngineExecutionAck:
        key = (
            self.namespace,
            service_principal,
            command.operation.tenant_id,
            command.operation.operation_id,
            command.operation.idempotency_key,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT command_digest, ack_json
                    FROM engine_submission
                    WHERE namespace = ?
                      AND service_principal = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                    """,
                    key,
                ).fetchone()
                if row is not None:
                    try:
                        stored_payload = json.loads(row["command_json"])
                        stored_command = EngineExecutionCommand.from_dict(
                            stored_payload
                        )
                    except (json.JSONDecodeError, EngineServiceError) as exc:
                        raise EngineServiceError(
                            "stored engine submission is corrupt"
                        ) from exc
                    if (
                        stored_command.submission_digest
                        != command.submission_digest
                    ):
                        raise EngineSubmissionConflict(
                            "engine idempotency identity was reused with different command"
                        )
                    existing = self._ack_from_dict(
                        json.loads(row["ack_json"])
                    )
                    self._connection.execute("COMMIT")
                    return existing
                self._connection.execute(
                    """
                    INSERT INTO engine_submission(
                        namespace, service_principal, tenant_id,
                        operation_id, idempotency_key, execution_id,
                        command_digest, command_json, ack_json, accepted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        *key,
                        command.execution_request.execution_id,
                        command.submission_digest,
                        json.dumps(
                            command.as_dict(),
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            ack.as_dict(),
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ),
                        ack.accepted_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return ack
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise EngineSubmissionConflict(
                    "engine execution identity already belongs to another submission"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise


    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> EngineToolApproval:
        return EngineToolApproval(
            approval_id=row["approval_id"],
            execution_id=row["execution_id"],
            call_id=row["call_id"],
            tool_id=row["tool_id"],
            arguments_digest=row["arguments_digest"],
            actor_id=row["actor_id"],
            tenant_id=row["tenant_id"],
            idempotency_key=row["idempotency_key"],
            bound_approval_ref=row["approval_ref"],
            issued_at=_aware(row["issued_at"], "approval.issued_at"),
            expires_at=_aware(row["expires_at"], "approval.expires_at"),
        )

    def remember_approval(
        self,
        approval: EngineToolApproval,
    ) -> EngineToolApproval:
        if not isinstance(approval, EngineToolApproval):
            raise TypeError("approval must be EngineToolApproval")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM engine_tool_approval
                    WHERE namespace = ?
                      AND execution_id = ?
                      AND call_id = ?
                      AND idempotency_key = ?
                    """,
                    (
                        self.namespace,
                        approval.execution_id,
                        approval.call_id,
                        approval.idempotency_key,
                    ),
                ).fetchone()
                if row is not None:
                    existing = self._approval_from_row(row)
                    stable_existing = (
                        existing.approval_id,
                        existing.execution_id,
                        existing.call_id,
                        existing.tool_id,
                        existing.arguments_digest,
                        existing.actor_id,
                        existing.tenant_id,
                        existing.idempotency_key,
                        existing.approval_ref,
                        existing.expires_at,
                    )
                    stable_candidate = (
                        approval.approval_id,
                        approval.execution_id,
                        approval.call_id,
                        approval.tool_id,
                        approval.arguments_digest,
                        approval.actor_id,
                        approval.tenant_id,
                        approval.idempotency_key,
                        approval.approval_ref,
                        approval.expires_at,
                    )
                    if stable_existing != stable_candidate:
                        raise EngineSubmissionConflict(
                            "approval idempotency identity was reused differently"
                        )
                    self._connection.execute("COMMIT")
                    return existing
                self._connection.execute(
                    """
                    INSERT INTO engine_tool_approval(
                        namespace, approval_id, execution_id, call_id,
                        tool_id, arguments_digest, actor_id, tenant_id,
                        idempotency_key, approval_ref, issued_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        approval.approval_id,
                        approval.execution_id,
                        approval.call_id,
                        approval.tool_id,
                        approval.arguments_digest,
                        approval.actor_id,
                        approval.tenant_id,
                        approval.idempotency_key,
                        approval.approval_ref,
                        approval.issued_at.isoformat(),
                        approval.expires_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return approval
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise EngineSubmissionConflict(
                    "engine tool approval identity conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def approvals(
        self,
        execution_id: str,
        *,
        now: datetime | None = None,
        include_expired: bool = False,
    ) -> tuple[EngineToolApproval, ...]:
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else _aware(now, "approval.now")
        )
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM engine_tool_approval
                WHERE namespace = ? AND execution_id = ?
                ORDER BY issued_at DESC, approval_id DESC
                """,
                (self.namespace, str(execution_id)),
            ).fetchall()
        approvals = tuple(self._approval_from_row(row) for row in rows)
        if include_expired:
            return approvals
        return tuple(
            approval
            for approval in approvals
            if not approval.expired(now=instant)
        )

    def active_approval_refs(
        self,
        execution_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        refs: dict[str, str] = {}
        for approval in self.approvals(
            execution_id,
            now=now,
            include_expired=False,
        ):
            refs.setdefault(approval.call_id, approval.approval_ref)
        return refs

    def close(self) -> None:
        with self._lock:
            self._connection.close()


def _operation_state(execution_state: ExecutionState) -> OperationState:
    if execution_state is ExecutionState.CREATED:
        return OperationState.ADMITTED
    if execution_state in {
        ExecutionState.LOADING,
        ExecutionState.ASSEMBLING_CONTEXT,
        ExecutionState.ROUTING,
        ExecutionState.PROVIDER_PENDING,
        ExecutionState.PROVIDER_COMPLETED,
        ExecutionState.CLASSIFYING_OUTPUT,
        ExecutionState.TOOL_PENDING,
        ExecutionState.TOOL_COMPLETED,
        ExecutionState.CHECKPOINTING,
        ExecutionState.VERIFYING,
        ExecutionState.REPAIRING,
        ExecutionState.FINALIZING,
    }:
        return OperationState.RUNNING
    if execution_state is ExecutionState.WAITING_FOR_TOOL_AUTHORITY:
        return OperationState.WAITING_FOR_TOOL
    if execution_state is ExecutionState.WAITING_FOR_USER:
        return OperationState.WAITING_FOR_USER
    if execution_state is ExecutionState.DEGRADED:
        return OperationState.DEGRADED
    if execution_state is ExecutionState.COMPLETED:
        return OperationState.COMPLETED
    if execution_state is ExecutionState.FAILED:
        return OperationState.FAILED
    if execution_state is ExecutionState.CANCELLED:
        return OperationState.CANCELLED
    return OperationState.RUNNING


class EngineExecutionService:
    """Authenticated durable engine submit/status/cancel/events boundary."""

    def __init__(
        self,
        repository: SQLiteExecutionRepository,
        submissions: SQLiteEngineSubmissionStore,
        authorities: EngineAuthorityRegistry,
    ) -> None:
        if not isinstance(repository, SQLiteExecutionRepository):
            raise TypeError("repository must be SQLiteExecutionRepository")
        if not isinstance(submissions, SQLiteEngineSubmissionStore):
            raise TypeError("submissions must be SQLiteEngineSubmissionStore")
        if not isinstance(authorities, EngineAuthorityRegistry):
            raise TypeError("authorities must be EngineAuthorityRegistry")
        self.repository = repository
        self.submissions = submissions
        self.authorities = authorities

    def _validate(
        self,
        stored_or_command: EngineExecutionCommand,
        *,
        verified_service_principal: str,
        required_scope: str,
        now: datetime | None = None,
    ) -> None:
        self.authorities.validate(
            verified_service_principal=verified_service_principal,
            authority=stored_or_command.delegated_authority,
            operation=stored_or_command.operation,
            execution_request=stored_or_command.execution_request,
            required_scope=required_scope,
            now=now,
        )

    def submit(
        self,
        command: EngineExecutionCommand,
        *,
        verified_service_principal: str,
        actor_id: str | None = None,
        tenant_id: str | None = None,
        now: datetime | None = None,
    ) -> EngineExecutionAck:
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        self._validate(
            command,
            verified_service_principal=verified_service_principal,
            required_scope="engine:submit",
            now=instant,
        )
        if actor_id is not None and str(actor_id).strip() != command.operation.actor_id:
            raise EngineAuthorityError(
                "submitted actor does not match delegated operation actor"
            )
        if tenant_id is not None and str(tenant_id).strip() != command.operation.tenant_id:
            raise EngineAuthorityError(
                "submitted tenant does not match delegated operation tenant"
            )
        existing = self.submissions.get(
            service_principal=verified_service_principal,
            tenant_id=command.operation.tenant_id,
            operation_id=command.operation.operation_id,
            idempotency_key=command.operation.idempotency_key,
        )
        if existing is not None:
            if (
                existing.command.submission_digest
                != command.submission_digest
            ):
                raise EngineSubmissionConflict(
                    "engine idempotency identity was reused with different command"
                )
            return existing.ack

        try:
            execution = self.repository.create(
                command.execution_request,
                now=instant,
            )
        except ExecutionRepositoryConflict as exc:
            raise EngineSubmissionConflict(str(exc)) from exc

        idempotency_digest = _digest(
            {
                "service_principal": verified_service_principal,
                "tenant_id": command.operation.tenant_id,
                "operation_id": command.operation.operation_id,
                "idempotency_key": command.operation.idempotency_key,
                "submission_digest": command.submission_digest,
            }
        )
        ack = EngineExecutionAck(
            operation_id=command.operation.operation_id,
            execution_id=execution.execution_id,
            state=_operation_state(execution.state).value,
            accepted_at=instant,
            idempotency_digest=idempotency_digest,
            status_ref=(
                "/api/v1/engine/executions/"
                + execution.execution_id
            ),
            events_ref=(
                "/api/v1/engine/executions/"
                + execution.execution_id
                + "/events"
            ),
            trace_id=command.operation.trace_id,
        )
        return self.submissions.remember(
            service_principal=verified_service_principal,
            command=command,
            ack=ack,
        )

    def _stored_for_access(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        scope: str,
        now: datetime | None = None,
        require_live_delegation: bool = False,
    ) -> _StoredSubmission:
        stored = self.submissions.get_by_execution_id(execution_id)
        if stored is None:
            raise EngineServiceError("unknown engine execution")
        if stored.principal != verified_service_principal:
            raise EngineServiceError(
                "engine execution belongs to a different service principal"
            )
        grant = self.authorities.grant_for(verified_service_principal)
        if scope not in grant.scopes:
            raise EngineServiceError("engine service grant is missing required scope")
        operation = stored.command.operation
        if not grant.allows_tenant(operation.tenant_id):
            raise EngineServiceError("tenant is outside engine service grant")
        if not grant.allows_capability(operation.capability):
            raise EngineServiceError("capability is outside engine service grant")
        if require_live_delegation:
            self._validate(
                stored.command,
                verified_service_principal=verified_service_principal,
                required_scope=scope,
                now=now,
            )
        return stored

    def pending_tool_approvals(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        actor_id: str,
        tenant_id: str,
        now: datetime | None = None,
    ) -> tuple[dict[str, str], ...]:
        stored = self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:read",
            now=now,
        )
        operation = stored.command.operation
        if (
            str(actor_id).strip() != operation.actor_id
            or str(tenant_id).strip() != operation.tenant_id
        ):
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        execution = self.repository.get(execution_id)
        if execution.state is not ExecutionState.WAITING_FOR_USER:
            return ()
        checkpoint = self.repository.latest_checkpoint(execution_id)
        if checkpoint is None:
            raise EngineServiceError(
                "waiting execution has no durable approval checkpoint"
            )
        payload = checkpoint.payload
        pending_ids = payload.get("pending_approval_call_ids", [])
        calls = payload.get("pending_tool_calls", [])
        if (
            not isinstance(pending_ids, list)
            or not isinstance(calls, list)
        ):
            raise EngineServiceError(
                "durable approval checkpoint is malformed"
            )
        wanted = {
            str(item)
            for item in pending_ids
            if isinstance(item, str) and item.strip()
        }
        rows: list[dict[str, str]] = []
        for raw in calls:
            if not isinstance(raw, Mapping):
                raise EngineServiceError(
                    "durable pending tool call is malformed"
                )
            call_id = str(raw.get("call_id") or "").strip()
            if call_id not in wanted:
                continue
            tool_id = str(raw.get("tool_id") or "").strip()
            digest = str(raw.get("arguments_digest") or "").strip()
            if (
                not call_id
                or not tool_id
                or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise EngineServiceError(
                    "durable pending tool call identity is malformed"
                )
            arguments = raw.get("arguments")
            if not isinstance(arguments, Mapping):
                raise EngineServiceError(
                    "durable pending tool call arguments are malformed"
                )
            idempotency_key = (
                execution_id + ":" + call_id + ":" + digest
            )
            try:
                operation_id = str(UUID(operation.operation_id))
            except (ValueError, AttributeError):
                operation_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        "skeleton-operation:" + operation.operation_id,
                    )
                )
            tool_request = ToolExecutionRequest(
                request_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        "skeleton-tool-request:"
                        + execution_id
                        + ":"
                        + call_id,
                    )
                ),
                operation_id=operation_id,
                tenant_id=operation.tenant_id,
                tool_id=tool_id,
                idempotency_key=idempotency_key,
                arguments=dict(arguments),
                requested_at=execution.updated_at,
                approval_ref=None,
                delegated_authority_ref=(
                    "execution:"
                    + execution_id
                    + ":provider-call:"
                    + call_id
                ),
            )
            rows.append(
                {
                    "call_id": call_id,
                    "tool_id": tool_id,
                    "arguments_digest": digest,
                    "idempotency_key": idempotency_key,
                    "approval_ref": approval_ref_for_request(tool_request),
                }
            )
        if len(rows) != len(wanted):
            raise EngineServiceError(
                "durable approval checkpoint is incomplete"
            )
        return tuple(rows)

    def approve_tool_call(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        actor_id: str,
        tenant_id: str,
        call_id: str,
        tool_id: str,
        arguments_digest: str,
        idempotency_key: str,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> EngineToolApproval:
        stored = self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:approve",
            now=now,
            require_live_delegation=True,
        )
        operation = stored.command.operation
        if (
            str(actor_id).strip() != operation.actor_id
            or str(tenant_id).strip() != operation.tenant_id
        ):
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else _aware(now, "approval.now")
        )
        expiry = _aware(expires_at, "approval.expires_at")
        if expiry <= instant:
            raise EngineServiceError(
                "tool approval is already expired"
            )
        delegation_expiry = stored.command.delegated_authority.expires_at
        operation_deadline = stored.command.operation.deadline
        authority_ceiling = min(delegation_expiry, operation_deadline)
        if expiry > authority_ceiling:
            raise EngineServiceError(
                "tool approval expiry exceeds delegated authority window"
            )
        pending = {
            row["call_id"]: row
            for row in self.pending_tool_approvals(
                execution_id,
                verified_service_principal=verified_service_principal,
                actor_id=operation.actor_id,
                tenant_id=operation.tenant_id,
                now=instant,
            )
        }
        call_key = str(call_id).strip()
        expected = pending.get(call_key)
        if expected is None:
            raise EngineServiceError(
                "tool call is not awaiting approval"
            )
        tool_key = str(tool_id).strip()
        digest = str(arguments_digest).strip()
        if (
            expected["tool_id"] != tool_key
            or expected["arguments_digest"] != digest
        ):
            raise EngineServiceError(
                "tool approval does not match pending call identity"
            )
        idem = str(idempotency_key).strip()
        if not idem or len(idem) > 1024:
            raise EngineServiceError(
                "approval idempotency_key is invalid"
            )
        if idem != expected["idempotency_key"]:
            raise EngineServiceError(
                "approval idempotency_key does not match pending call"
            )
        approval_id = str(
            uuid5(
                NAMESPACE_URL,
                "skeleton-engine-tool-approval:"
                + execution_id
                + ":"
                + call_key
                + ":"
                + idem,
            )
        )
        approval = EngineToolApproval(
            approval_id=approval_id,
            execution_id=execution_id,
            call_id=call_key,
            tool_id=tool_key,
            arguments_digest=digest,
            actor_id=stored.command.operation.actor_id,
            tenant_id=stored.command.operation.tenant_id,
            idempotency_key=idem,
            bound_approval_ref=expected["approval_ref"],
            issued_at=instant,
            expires_at=expiry,
        )
        return self.submissions.remember_approval(approval)

    def active_approval_refs(
        self,
        execution_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else _aware(now, "approval.now")
        )
        stored = self.submissions.get_by_execution_id(execution_id)
        if stored is None:
            return {}
        if stored.command.delegated_authority.expired(now=instant):
            return {}
        if instant >= stored.command.operation.deadline:
            return {}
        return self.submissions.active_approval_refs(
            execution_id,
            now=instant,
        )

    def status(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        actor_id: str | None = None,
        tenant_id: str | None = None,
        now: datetime | None = None,
    ) -> EngineExecutionStatus:
        stored = self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:read",
            now=now,
        )
        operation = stored.command.operation
        if actor_id is not None and str(actor_id).strip() != operation.actor_id:
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        if tenant_id is not None and str(tenant_id).strip() != operation.tenant_id:
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        execution = self.repository.get(execution_id)
        result = self.repository.result(execution_id)
        failure_code = None
        if result is not None and result.status == "failed":
            raw = result.usage.get("error_code")
            if isinstance(raw, str):
                failure_code = raw
        return EngineExecutionStatus(
            operation_id=stored.command.operation.operation_id,
            execution_id=execution.execution_id,
            operation_state=_operation_state(execution.state).value,
            execution_state=execution.state.value,
            latest_checkpoint_version=execution.checkpoint_version,
            result_ref=(
                None
                if result is None
                else "execution-result:" + execution.execution_id
            ),
            failure_code=failure_code,
            updated_at=execution.updated_at,
            cancellation_requested=execution.cancellation_requested,
        )

    def cancel(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        actor_id: str | None = None,
        tenant_id: str | None = None,
        now: datetime | None = None,
    ) -> EngineExecutionStatus:
        stored = self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:cancel",
            now=now,
            require_live_delegation=True,
        )
        operation = stored.command.operation
        if actor_id is not None and str(actor_id).strip() != operation.actor_id:
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        if tenant_id is not None and str(tenant_id).strip() != operation.tenant_id:
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        current = self.repository.get(execution_id)
        if not current.terminal and not current.cancellation_requested:
            self.repository.request_cancel(
                execution_id,
                expected_version=current.version,
                now=now,
            )
        return self.status(
            execution_id,
            verified_service_principal=verified_service_principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
            now=now,
        )

    def events(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        actor_id: str | None = None,
        tenant_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stored = self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:events",
            now=now,
        )
        operation = stored.command.operation
        if actor_id is not None and str(actor_id).strip() != operation.actor_id:
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        if tenant_id is not None and str(tenant_id).strip() != operation.tenant_id:
            raise EngineServiceError(
                "engine execution belongs to a different actor or tenant"
            )
        execution = self.repository.get(execution_id)
        turns = self.repository.turns(execution_id)
        checkpoint = self.repository.latest_checkpoint(execution_id)
        result = self.repository.result(execution_id)
        terminal = self.repository.pending_outbox(
            execution_id=execution_id,
        )
        events: list[dict[str, Any]] = []
        events.append(
            {
                "event_id": "execution:" + execution_id + ":state",
                "sequence": 0,
                "type": "execution.state",
                "state": execution.state.value,
                "version": execution.version,
                "updated_at": execution.updated_at.isoformat(),
            }
        )
        for index, turn in enumerate(turns, start=1):
            events.append(
                {
                    "event_id": "turn:" + turn.turn_id,
                    "sequence": index,
                    "type": "execution.turn",
                    "turn": turn.as_dict(),
                }
            )
        next_sequence = len(events)
        if checkpoint is not None:
            events.append(
                {
                    "event_id": checkpoint.checkpoint_ref,
                    "sequence": next_sequence,
                    "type": "execution.checkpoint",
                    "checkpoint": checkpoint.as_dict(),
                }
            )
            next_sequence += 1
        if result is not None:
            events.append(
                {
                    "event_id": "execution-result:" + execution_id,
                    "sequence": next_sequence,
                    "type": "execution.result",
                    "result": result.as_dict(),
                }
            )
            next_sequence += 1
        for outbox in terminal:
            events.append(
                {
                    "event_id": "outbox:" + outbox.outbox_id,
                    "sequence": next_sequence,
                    "type": outbox.event_type,
                    "payload": dict(outbox.payload),
                    "created_at": outbox.created_at.isoformat(),
                }
            )
            next_sequence += 1
        return {
            "execution_id": execution_id,
            "events": events,
            "next_sequence": next_sequence,
        }


__all__ = [
    "EngineContextHandoff",
    "EngineExecutionAck",
    "EngineExecutionCommand",
    "EngineExecutionService",
    "EngineExecutionStatus",
    "EngineServiceError",
    "EngineSubmissionConflict",
    "EngineToolApproval",
    "SQLiteEngineSubmissionStore",
]
