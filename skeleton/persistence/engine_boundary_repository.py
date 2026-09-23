"""Durable engine-boundary submission and cancellation ledger."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from skeleton.contracts.engine_boundary import (
    EngineCancelCommand,
    EngineExecutionAck,
    EngineExecutionCommand,
)
from skeleton.contracts.operation import (
    OperationEnvelope,
    OperationState,
    TERMINAL_OPERATION_STATES,
)


class EngineBoundaryRepositoryError(RuntimeError):
    """Base engine boundary repository error."""


class EngineBoundaryRepositoryConflict(
    EngineBoundaryRepositoryError
):
    """A durable engine boundary identity was reused incompatibly."""


def _parse_time(raw: object, field: str) -> datetime:
    if not isinstance(raw, str):
        raise EngineBoundaryRepositoryError(
            f"{field} must be ISO text"
        )
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EngineBoundaryRepositoryError(
            f"{field} is invalid"
        ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise EngineBoundaryRepositoryError(
            f"{field} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _operation_from_json(raw: object) -> OperationEnvelope:
    if not isinstance(raw, str):
        raise EngineBoundaryRepositoryError(
            "operation_json must be text"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EngineBoundaryRepositoryError(
            "operation_json is invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise EngineBoundaryRepositoryError(
            "operation_json must be an object"
        )
    return OperationEnvelope(
        operation_id=payload["operation_id"],
        tenant_id=payload["tenant_id"],
        actor_id=payload["actor_id"],
        capability=payload["capability"],
        created_at=_parse_time(
            payload["created_at"],
            "created_at",
        ),
        deadline=_parse_time(
            payload["deadline"],
            "deadline",
        ),
        idempotency_key=payload["idempotency_key"],
        trace_id=payload["trace_id"],
        state=OperationState(payload["state"]),
    )


def _ack_from_json(raw: object) -> EngineExecutionAck:
    if not isinstance(raw, str):
        raise EngineBoundaryRepositoryError(
            "ack_json must be text"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EngineBoundaryRepositoryError(
            "ack_json is invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise EngineBoundaryRepositoryError(
            "ack_json must be an object"
        )
    return EngineExecutionAck(
        operation_id=payload["operation_id"],
        execution_id=payload["execution_id"],
        state=OperationState(payload["state"]),
        accepted_at=_parse_time(
            payload["accepted_at"],
            "accepted_at",
        ),
        idempotency_digest=payload[
            "idempotency_digest"
        ],
        status_ref=payload["status_ref"],
        events_ref=payload["events_ref"],
        trace_id=payload["trace_id"],
        schema_version=int(payload.get("schema_version", 1)),
    )


class SQLiteEngineBoundaryRepository:
    """Durable API-boundary identity and operation-state authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "engine_boundary",
    ) -> None:
        normalized = str(namespace).strip()
        if not normalized:
            raise ValueError("namespace must not be empty")
        self.namespace = normalized
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
                    operation_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    idempotency_digest TEXT NOT NULL,
                    authority_digest TEXT NOT NULL,
                    command_digest TEXT NOT NULL,
                    operation_json TEXT NOT NULL,
                    ack_json TEXT NOT NULL,
                    operation_state TEXT NOT NULL,
                    accepted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_id),
                    UNIQUE(
                        namespace,
                        tenant_id,
                        actor_id,
                        capability,
                        idempotency_key
                    ),
                    UNIQUE(namespace, execution_id)
                );

                CREATE TABLE IF NOT EXISTS engine_cancel_receipt (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    PRIMARY KEY(
                        namespace,
                        operation_id,
                        idempotency_key
                    )
                );
                """
            )

    @staticmethod
    def _command_digest(
        command: EngineExecutionCommand,
    ) -> str:
        import hashlib

        encoded = json.dumps(
            command.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def submit(
        self,
        command: EngineExecutionCommand,
        ack: EngineExecutionAck,
        *,
        now: datetime | None = None,
    ) -> EngineExecutionAck:
        if not isinstance(command, EngineExecutionCommand):
            raise TypeError(
                "command must be EngineExecutionCommand"
            )
        if not isinstance(ack, EngineExecutionAck):
            raise TypeError("ack must be EngineExecutionAck")
        if (
            ack.operation_id
            != command.operation.operation_id
            or ack.execution_id
            != command.execution_request.execution_id
            or ack.idempotency_digest
            != command.idempotency_digest
            or ack.trace_id
            != command.operation.trace_id
        ):
            raise EngineBoundaryRepositoryConflict(
                "ack does not match execution command"
            )

        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        command_digest = self._command_digest(command)
        operation = command.operation
        key = (
            self.namespace,
            operation.operation_id,
        )

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    """
                    SELECT * FROM engine_submission
                    WHERE namespace = ?
                      AND operation_id = ?
                    """,
                    key,
                ).fetchone()
                if existing is not None:
                    if (
                        existing["idempotency_digest"]
                        != command.idempotency_digest
                        or existing["command_digest"]
                        != command_digest
                        or existing["authority_digest"]
                        != command.delegated_authority.authority_digest
                    ):
                        raise EngineBoundaryRepositoryConflict(
                            "operation_id replayed with different command"
                        )
                    stored = _ack_from_json(
                        existing["ack_json"]
                    )
                    self._connection.execute("COMMIT")
                    return stored

                by_idempotency = self._connection.execute(
                    """
                    SELECT * FROM engine_submission
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND actor_id = ?
                      AND capability = ?
                      AND idempotency_key = ?
                    """,
                    (
                        self.namespace,
                        operation.tenant_id,
                        operation.actor_id,
                        operation.capability,
                        operation.idempotency_key,
                    ),
                ).fetchone()
                if by_idempotency is not None:
                    if (
                        by_idempotency["idempotency_digest"]
                        != command.idempotency_digest
                        or by_idempotency["command_digest"]
                        != command_digest
                    ):
                        raise EngineBoundaryRepositoryConflict(
                            "idempotency key replayed with different command"
                        )
                    stored = _ack_from_json(
                        by_idempotency["ack_json"]
                    )
                    self._connection.execute("COMMIT")
                    return stored

                self._connection.execute(
                    """
                    INSERT INTO engine_submission(
                        namespace, operation_id, execution_id,
                        tenant_id, actor_id, capability,
                        idempotency_key, idempotency_digest,
                        authority_digest, command_digest,
                        operation_json, ack_json,
                        operation_state, accepted_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        operation.operation_id,
                        command.execution_request.execution_id,
                        operation.tenant_id,
                        operation.actor_id,
                        operation.capability,
                        operation.idempotency_key,
                        command.idempotency_digest,
                        command.delegated_authority.authority_digest,
                        command_digest,
                        json.dumps(
                            operation.as_dict(),
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
                        ack.state.value,
                        ack.accepted_at.isoformat(),
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return ack
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise EngineBoundaryRepositoryConflict(
                    "engine submission identity conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def ack(
        self,
        operation_id: str,
    ) -> EngineExecutionAck:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT ack_json FROM engine_submission
                WHERE namespace = ?
                  AND operation_id = ?
                """,
                (
                    self.namespace,
                    str(operation_id),
                ),
            ).fetchone()
            if row is None:
                raise EngineBoundaryRepositoryError(
                    "unknown operation"
                )
            return _ack_from_json(row["ack_json"])

    def operation(
        self,
        operation_id: str,
    ) -> OperationEnvelope:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT operation_json, operation_state
                FROM engine_submission
                WHERE namespace = ?
                  AND operation_id = ?
                """,
                (
                    self.namespace,
                    str(operation_id),
                ),
            ).fetchone()
            if row is None:
                raise EngineBoundaryRepositoryError(
                    "unknown operation"
                )
            original = _operation_from_json(
                row["operation_json"]
            )
            return OperationEnvelope(
                operation_id=original.operation_id,
                tenant_id=original.tenant_id,
                actor_id=original.actor_id,
                capability=original.capability,
                created_at=original.created_at,
                deadline=original.deadline,
                idempotency_key=original.idempotency_key,
                trace_id=original.trace_id,
                state=OperationState(
                    row["operation_state"]
                ),
            )

    def execution_id(
        self,
        operation_id: str,
    ) -> str:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT execution_id
                FROM engine_submission
                WHERE namespace = ?
                  AND operation_id = ?
                """,
                (
                    self.namespace,
                    str(operation_id),
                ),
            ).fetchone()
            if row is None:
                raise EngineBoundaryRepositoryError(
                    "unknown operation"
                )
            return str(row["execution_id"])

    def update_operation_state(
        self,
        operation_id: str,
        target: OperationState | str,
        *,
        now: datetime | None = None,
    ) -> OperationEnvelope:
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.operation(operation_id)
                target_state = OperationState(target)
                if current.state is target_state:
                    self._connection.execute("COMMIT")
                    return current
                if current.state in TERMINAL_OPERATION_STATES:
                    raise EngineBoundaryRepositoryConflict(
                        "terminal operation cannot transition"
                    )
                updated = current.transition(target_state)
                self._connection.execute(
                    """
                    UPDATE engine_submission
                    SET operation_state = ?, updated_at = ?
                    WHERE namespace = ?
                      AND operation_id = ?
                    """,
                    (
                        target_state.value,
                        instant.isoformat(),
                        self.namespace,
                        operation_id,
                    ),
                )
                self._connection.execute("COMMIT")
                return updated
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def force_terminal_state(
        self,
        operation_id: str,
        target: OperationState | str,
        *,
        now: datetime | None = None,
    ) -> OperationEnvelope:
        target_state = OperationState(target)
        if target_state not in TERMINAL_OPERATION_STATES:
            raise ValueError(
                "force_terminal_state requires terminal target"
            )
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.operation(operation_id)
                if current.state is target_state:
                    self._connection.execute("COMMIT")
                    return current
                if current.state in TERMINAL_OPERATION_STATES:
                    raise EngineBoundaryRepositoryConflict(
                        "operation already terminal differently"
                    )
                self._connection.execute(
                    """
                    UPDATE engine_submission
                    SET operation_state = ?, updated_at = ?
                    WHERE namespace = ?
                      AND operation_id = ?
                    """,
                    (
                        target_state.value,
                        instant.isoformat(),
                        self.namespace,
                        operation_id,
                    ),
                )
                self._connection.execute("COMMIT")
                return OperationEnvelope(
                    operation_id=current.operation_id,
                    tenant_id=current.tenant_id,
                    actor_id=current.actor_id,
                    capability=current.capability,
                    created_at=current.created_at,
                    deadline=current.deadline,
                    idempotency_key=current.idempotency_key,
                    trace_id=current.trace_id,
                    state=target_state,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def cancel(
        self,
        command: EngineCancelCommand,
        *,
        now: datetime | None = None,
    ) -> OperationEnvelope:
        if not isinstance(command, EngineCancelCommand):
            raise TypeError(
                "command must be EngineCancelCommand"
            )
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                operation = self.operation(
                    command.operation_id
                )
                if (
                    operation.actor_id != command.actor_id
                    or operation.tenant_id
                    != command.tenant_id
                ):
                    raise EngineBoundaryRepositoryConflict(
                        "cancel identity does not match operation"
                    )

                existing = self._connection.execute(
                    """
                    SELECT * FROM engine_cancel_receipt
                    WHERE namespace = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                    """,
                    (
                        self.namespace,
                        command.operation_id,
                        command.idempotency_key,
                    ),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["actor_id"]
                        != command.actor_id
                        or existing["tenant_id"]
                        != command.tenant_id
                        or existing["reason"]
                        != command.reason
                    ):
                        raise EngineBoundaryRepositoryConflict(
                            "cancel idempotency key replayed differently"
                        )
                    self._connection.execute("COMMIT")
                    return self.operation(
                        command.operation_id
                    )

                if operation.state in TERMINAL_OPERATION_STATES:
                    self._connection.execute(
                        """
                        INSERT INTO engine_cancel_receipt(
                            namespace, operation_id,
                            idempotency_key, actor_id,
                            tenant_id, reason,
                            requested_at, state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.namespace,
                            command.operation_id,
                            command.idempotency_key,
                            command.actor_id,
                            command.tenant_id,
                            command.reason,
                            command.requested_at.isoformat(),
                            operation.state.value,
                        ),
                    )
                    self._connection.execute("COMMIT")
                    return operation

                self._connection.execute(
                    """
                    INSERT INTO engine_cancel_receipt(
                        namespace, operation_id,
                        idempotency_key, actor_id,
                        tenant_id, reason,
                        requested_at, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        command.operation_id,
                        command.idempotency_key,
                        command.actor_id,
                        command.tenant_id,
                        command.reason,
                        command.requested_at.isoformat(),
                        OperationState.CANCELLED.value,
                    ),
                )
                self._connection.execute(
                    """
                    UPDATE engine_submission
                    SET operation_state = ?, updated_at = ?
                    WHERE namespace = ?
                      AND operation_id = ?
                    """,
                    (
                        OperationState.CANCELLED.value,
                        instant.isoformat(),
                        self.namespace,
                        command.operation_id,
                    ),
                )
                self._connection.execute("COMMIT")
                return OperationEnvelope(
                    operation_id=operation.operation_id,
                    tenant_id=operation.tenant_id,
                    actor_id=operation.actor_id,
                    capability=operation.capability,
                    created_at=operation.created_at,
                    deadline=operation.deadline,
                    idempotency_key=operation.idempotency_key,
                    trace_id=operation.trace_id,
                    state=OperationState.CANCELLED,
                )
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise EngineBoundaryRepositoryConflict(
                    "cancel receipt conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "EngineBoundaryRepositoryConflict",
    "EngineBoundaryRepositoryError",
    "SQLiteEngineBoundaryRepository",
]
