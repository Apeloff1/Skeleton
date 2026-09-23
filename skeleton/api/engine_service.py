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
class EngineExecutionCommand:
    operation: OperationEnvelope
    execution_request: AIExecutionRequest
    delegated_authority: DelegatedAuthority
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
        return _digest(self.as_dict(include_authority_digest=True))

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
                    if row["command_digest"] != command.command_digest:
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
                        command.command_digest,
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
        existing = self.submissions.get(
            service_principal=verified_service_principal,
            tenant_id=command.operation.tenant_id,
            operation_id=command.operation.operation_id,
            idempotency_key=command.operation.idempotency_key,
        )
        if existing is not None:
            if existing.command.command_digest != command.command_digest:
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
                "command_digest": command.command_digest,
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
    ) -> _StoredSubmission:
        stored = self.submissions.get_by_execution_id(execution_id)
        if stored is None:
            raise EngineServiceError("unknown engine execution")
        self._validate(
            stored.command,
            verified_service_principal=verified_service_principal,
            required_scope=scope,
            now=now,
        )
        return stored

    def status(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        now: datetime | None = None,
    ) -> EngineExecutionStatus:
        stored = self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:read",
            now=now,
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
        now: datetime | None = None,
    ) -> EngineExecutionStatus:
        self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:cancel",
            now=now,
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
            now=now,
        )

    def events(
        self,
        execution_id: str,
        *,
        verified_service_principal: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._stored_for_access(
            execution_id,
            verified_service_principal=verified_service_principal,
            scope="engine:events",
            now=now,
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
    "EngineExecutionAck",
    "EngineExecutionCommand",
    "EngineExecutionService",
    "EngineExecutionStatus",
    "EngineServiceError",
    "EngineSubmissionConflict",
    "SQLiteEngineSubmissionStore",
]
