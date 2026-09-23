"""Durable cognitive-execution repository and finalization outbox.

The execution repository is authoritative for execution state, turn lineage,
checkpoints, terminal results, and retry-stable finalization events. SQLite is
the deterministic reference implementation; higher-scale stores must preserve
the same compare-and-set and transactional semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.ai_execution import (
    AIExecution,
    AIExecutionRequest,
    AIExecutionResult,
    AgentTurn,
    ExecutionCheckpoint,
    ExecutionState,
)


class ExecutionRepositoryError(RuntimeError):
    """Base durable execution repository failure."""


class ExecutionRepositoryConflict(ExecutionRepositoryError):
    """Execution identity/version/lineage conflict."""


class ExecutionRepositoryCorruption(ExecutionRepositoryError):
    """Persisted execution state cannot be interpreted safely."""


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if (
        not isinstance(instant, datetime)
        or instant.tzinfo is None
        or instant.utcoffset() is None
    ):
        raise ExecutionRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _parse_time(raw: object, field: str) -> datetime:
    if not isinstance(raw, str):
        raise ExecutionRepositoryCorruption(f"{field} must be ISO text")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ExecutionRepositoryCorruption(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionRepositoryCorruption(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionRepositoryError("value must be deterministic JSON") from exc


def _json_object(raw: object, field: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ExecutionRepositoryCorruption(f"{field} must be JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExecutionRepositoryCorruption(f"{field} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ExecutionRepositoryCorruption(f"{field} must be an object")
    return value


def _json_array(raw: object, field: str) -> list[Any]:
    if not isinstance(raw, str):
        raise ExecutionRepositoryCorruption(f"{field} must be JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExecutionRepositoryCorruption(f"{field} is invalid JSON") from exc
    if not isinstance(value, list):
        raise ExecutionRepositoryCorruption(f"{field} must be an array")
    return value


def _outbox_id(namespace: str, execution_id: str, version: int, kind: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"skeleton-execution-outbox:{namespace}:{execution_id}:{kind}:{version}",
        )
    )


@dataclass(frozen=True, slots=True)
class ExecutionOutboxEvent:
    outbox_id: str
    execution_id: str
    execution_version: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    published_at: datetime | None = None

    @property
    def published(self) -> bool:
        return self.published_at is not None


class SQLiteExecutionRepository:
    """Authoritative reference store for cognitive execution state."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "ai_execution",
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
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS ai_execution_state (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    identity_digest TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    latest_turn_index INTEGER NOT NULL,
                    checkpoint_version INTEGER NOT NULL,
                    cancellation_requested INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, execution_id),
                    UNIQUE(namespace, operation_id, execution_id)
                );

                CREATE TABLE IF NOT EXISTS ai_execution_turn (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    parent_turn_id TEXT,
                    turn_json TEXT NOT NULL,
                    PRIMARY KEY(namespace, execution_id, turn_id),
                    UNIQUE(namespace, execution_id, turn_index),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_execution_checkpoint (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    checkpoint_version INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, execution_id, checkpoint_version),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_execution_result (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, execution_id),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_execution_outbox (
                    namespace TEXT NOT NULL,
                    outbox_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    execution_version INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    PRIMARY KEY(namespace, outbox_id),
                    UNIQUE(namespace, execution_id, event_type, execution_version),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_ai_execution_outbox_pending
                ON ai_execution_outbox(namespace, published_at, created_at);
                """
            )

    @staticmethod
    def _request_from_dict(payload: dict[str, Any]) -> AIExecutionRequest:
        return AIExecutionRequest(
            operation_id=payload["operation_id"],
            execution_id=payload["execution_id"],
            objective=payload["objective"],
            context_policy=payload["context_policy"],
            tool_policy=payload["tool_policy"],
            resource_budget=payload["resource_budget"],
            stop_policy=payload["stop_policy"],
            checkpoint_ref=payload.get("checkpoint_ref"),
            created_at=_parse_time(payload["created_at"], "created_at"),
        )

    def _execution_from_row(self, row: sqlite3.Row) -> AIExecution:
        try:
            request_payload = _json_object(row["request_json"], "request_json")
            request = self._request_from_dict(request_payload)
            if request.identity_digest != row["identity_digest"]:
                raise ExecutionRepositoryCorruption(
                    "persisted execution identity digest mismatch"
                )
            return AIExecution(
                request=request,
                state=ExecutionState(row["state"]),
                version=int(row["version"]),
                latest_turn_index=int(row["latest_turn_index"]),
                checkpoint_version=int(row["checkpoint_version"]),
                cancellation_requested=bool(row["cancellation_requested"]),
                updated_at=_parse_time(row["updated_at"], "updated_at"),
            )
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption(
                "persisted execution violates contract"
            ) from exc

    @staticmethod
    def _turn_from_row(row: sqlite3.Row) -> AgentTurn:
        try:
            payload = _json_object(row["turn_json"], "turn_json")
            return AgentTurn(
                operation_id=payload["operation_id"],
                execution_id=payload["execution_id"],
                turn_id=payload["turn_id"],
                parent_turn_id=payload.get("parent_turn_id"),
                turn_index=int(payload["turn_index"]),
                phase=ExecutionState(payload["phase"]),
                context_digest=payload["context_digest"],
                route_decision_id=payload.get("route_decision_id"),
                provider_request_id=payload.get("provider_request_id"),
                provider_response_id=payload.get("provider_response_id"),
                tool_receipt_ids=tuple(payload.get("tool_receipt_ids") or ()),
                verification_receipt_id=payload.get("verification_receipt_id"),
                usage_delta=payload.get("usage_delta") or {},
                checkpoint_ref=payload["checkpoint_ref"],
                status=payload["status"],
            )
        except Exception as exc:
            raise ExecutionRepositoryCorruption(
                "persisted turn violates contract"
            ) from exc

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row) -> ExecutionCheckpoint:
        try:
            payload = _json_object(row["checkpoint_json"], "checkpoint_json")
            return ExecutionCheckpoint(
                operation_id=payload["operation_id"],
                execution_id=payload["execution_id"],
                checkpoint_version=int(payload["checkpoint_version"]),
                execution_version=int(payload["execution_version"]),
                state=ExecutionState(payload["state"]),
                latest_turn_index=int(payload["latest_turn_index"]),
                payload=payload["payload"],
                payload_digest=payload["payload_digest"],
                created_at=_parse_time(payload["created_at"], "created_at"),
            )
        except Exception as exc:
            raise ExecutionRepositoryCorruption(
                "persisted checkpoint violates contract"
            ) from exc

    @staticmethod
    def _result_from_row(row: sqlite3.Row) -> AIExecutionResult:
        try:
            payload = _json_object(row["result_json"], "result_json")
            return AIExecutionResult(
                operation_id=payload["operation_id"],
                execution_id=payload["execution_id"],
                status=payload["status"],
                final_output=payload.get("final_output"),
                verification=payload.get("verification"),
                route_receipts=tuple(payload.get("route_receipts") or ()),
                provider_receipts=tuple(payload.get("provider_receipts") or ()),
                tool_receipts=tuple(payload.get("tool_receipts") or ()),
                memory_refs=tuple(payload.get("memory_refs") or ()),
                artifact_refs=tuple(payload.get("artifact_refs") or ()),
                usage=payload.get("usage") or {},
                stream_terminal_event=payload.get("stream_terminal_event"),
                completed_at=_parse_time(payload["completed_at"], "completed_at"),
            )
        except Exception as exc:
            raise ExecutionRepositoryCorruption(
                "persisted result violates contract"
            ) from exc

    @staticmethod
    def _outbox_from_row(row: sqlite3.Row) -> ExecutionOutboxEvent:
        return ExecutionOutboxEvent(
            outbox_id=row["outbox_id"],
            execution_id=row["execution_id"],
            execution_version=int(row["execution_version"]),
            event_type=row["event_type"],
            payload=_json_object(row["payload_json"], "payload_json"),
            created_at=_parse_time(row["created_at"], "created_at"),
            published_at=(
                None
                if row["published_at"] is None
                else _parse_time(row["published_at"], "published_at")
            ),
        )

    def create(
        self,
        request: AIExecutionRequest,
        *,
        now: datetime | None = None,
    ) -> AIExecution:
        if not isinstance(request, AIExecutionRequest):
            raise TypeError("request must be AIExecutionRequest")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM ai_execution_state
                    WHERE namespace = ? AND execution_id = ?
                    """,
                    (self.namespace, request.execution_id),
                ).fetchone()
                if row is not None:
                    current = self._execution_from_row(row)
                    if current.request.identity_digest != request.identity_digest:
                        raise ExecutionRepositoryConflict(
                            "execution_id already exists with different request"
                        )
                    self._connection.execute("COMMIT")
                    return current

                self._connection.execute(
                    """
                    INSERT INTO ai_execution_state(
                        namespace, execution_id, operation_id, identity_digest,
                        request_json, state, version, latest_turn_index,
                        checkpoint_version, cancellation_requested, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, -1, 0, 0, ?)
                    """,
                    (
                        self.namespace,
                        request.execution_id,
                        request.operation_id,
                        request.identity_digest,
                        _json_dump(request.as_dict()),
                        ExecutionState.CREATED.value,
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return AIExecution(request=request, updated_at=instant)
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict(
                    "execution durable identity conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(self, execution_id: str) -> AIExecution:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM ai_execution_state
                WHERE namespace = ? AND execution_id = ?
                """,
                (self.namespace, str(execution_id)),
            ).fetchone()
            if row is None:
                raise ExecutionRepositoryError("unknown execution")
            return self._execution_from_row(row)

    def transition(
        self,
        execution_id: str,
        target: ExecutionState | str,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> AIExecution:
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(execution_id)
                if current.version != expected_version:
                    raise ExecutionRepositoryConflict(
                        "execution version changed before transition"
                    )
                updated = current.transition(target, now=instant)
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET state = ?, version = ?, updated_at = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        updated.state.value,
                        updated.version,
                        instant.isoformat(),
                        self.namespace,
                        execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict(
                        "execution version changed during transition"
                    )
                self._connection.execute("COMMIT")
                return updated
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def request_cancel(
        self,
        execution_id: str,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> AIExecution:
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(execution_id)
                if current.version != expected_version:
                    raise ExecutionRepositoryConflict(
                        "execution version changed before cancellation request"
                    )
                if current.terminal:
                    self._connection.execute("COMMIT")
                    return current
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET cancellation_requested = 1, version = ?, updated_at = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        current.version + 1,
                        instant.isoformat(),
                        self.namespace,
                        execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict(
                        "execution version changed during cancellation request"
                    )
                self._connection.execute("COMMIT")
                return AIExecution(
                    request=current.request,
                    state=current.state,
                    version=current.version + 1,
                    latest_turn_index=current.latest_turn_index,
                    checkpoint_version=current.checkpoint_version,
                    cancellation_requested=True,
                    updated_at=instant,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def append_turn(
        self,
        turn: AgentTurn,
        *,
        expected_execution_version: int,
        now: datetime | None = None,
    ) -> AIExecution:
        if not isinstance(turn, AgentTurn):
            raise TypeError("turn must be AgentTurn")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(turn.execution_id)
                if current.operation_id != turn.operation_id:
                    raise ExecutionRepositoryConflict(
                        "turn operation does not match execution"
                    )
                if current.version != expected_execution_version:
                    raise ExecutionRepositoryConflict(
                        "execution version changed before turn append"
                    )
                expected_turn_index = current.latest_turn_index + 1
                if turn.turn_index != expected_turn_index:
                    raise ExecutionRepositoryConflict(
                        "turn_index must strictly increase"
                    )
                if turn.turn_index > 0:
                    parent = self._connection.execute(
                        """
                        SELECT turn_id FROM ai_execution_turn
                        WHERE namespace = ? AND execution_id = ? AND turn_index = ?
                        """,
                        (
                            self.namespace,
                            turn.execution_id,
                            turn.turn_index - 1,
                        ),
                    ).fetchone()
                    if parent is None or parent["turn_id"] != turn.parent_turn_id:
                        raise ExecutionRepositoryConflict(
                            "turn parent does not match immutable lineage"
                        )
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_turn(
                        namespace, execution_id, turn_id, turn_index,
                        parent_turn_id, turn_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        turn.execution_id,
                        turn.turn_id,
                        turn.turn_index,
                        turn.parent_turn_id,
                        _json_dump(turn.as_dict()),
                    ),
                )
                next_version = current.version + 1
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET latest_turn_index = ?, version = ?, updated_at = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        turn.turn_index,
                        next_version,
                        instant.isoformat(),
                        self.namespace,
                        turn.execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict(
                        "execution changed during turn append"
                    )
                self._connection.execute("COMMIT")
                return AIExecution(
                    request=current.request,
                    state=current.state,
                    version=next_version,
                    latest_turn_index=turn.turn_index,
                    checkpoint_version=current.checkpoint_version,
                    cancellation_requested=current.cancellation_requested,
                    updated_at=instant,
                )
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict(
                    "turn identity or index already exists"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def turns(self, execution_id: str) -> tuple[AgentTurn, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM ai_execution_turn
                WHERE namespace = ? AND execution_id = ?
                ORDER BY turn_index ASC
                """,
                (self.namespace, execution_id),
            ).fetchall()
            return tuple(self._turn_from_row(row) for row in rows)

    def checkpoint(
        self,
        execution_id: str,
        payload: dict[str, Any],
        *,
        expected_execution_version: int,
        expected_checkpoint_version: int,
        now: datetime | None = None,
    ) -> ExecutionCheckpoint:
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(execution_id)
                if current.version != expected_execution_version:
                    raise ExecutionRepositoryConflict(
                        "execution version changed before checkpoint"
                    )
                if current.checkpoint_version != expected_checkpoint_version:
                    raise ExecutionRepositoryConflict(
                        "checkpoint version changed before compare-and-set"
                    )
                next_checkpoint_version = current.checkpoint_version + 1
                next_execution_version = current.version + 1
                checkpoint = ExecutionCheckpoint(
                    operation_id=current.operation_id,
                    execution_id=current.execution_id,
                    checkpoint_version=next_checkpoint_version,
                    execution_version=next_execution_version,
                    state=current.state,
                    latest_turn_index=current.latest_turn_index,
                    payload=payload,
                    created_at=instant,
                )
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_checkpoint(
                        namespace, execution_id, checkpoint_version,
                        checkpoint_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        execution_id,
                        next_checkpoint_version,
                        _json_dump(checkpoint.as_dict()),
                        instant.isoformat(),
                    ),
                )
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET checkpoint_version = ?, version = ?, updated_at = ?
                    WHERE namespace = ? AND execution_id = ?
                      AND version = ? AND checkpoint_version = ?
                    """,
                    (
                        next_checkpoint_version,
                        next_execution_version,
                        instant.isoformat(),
                        self.namespace,
                        execution_id,
                        current.version,
                        current.checkpoint_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict(
                        "execution changed during checkpoint compare-and-set"
                    )
                self._connection.execute("COMMIT")
                return checkpoint
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict(
                    "checkpoint identity conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def latest_checkpoint(
        self,
        execution_id: str,
    ) -> ExecutionCheckpoint | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM ai_execution_checkpoint
                WHERE namespace = ? AND execution_id = ?
                ORDER BY checkpoint_version DESC
                LIMIT 1
                """,
                (self.namespace, execution_id),
            ).fetchone()
            return None if row is None else self._checkpoint_from_row(row)

    def result(self, execution_id: str) -> AIExecutionResult | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM ai_execution_result
                WHERE namespace = ? AND execution_id = ?
                """,
                (self.namespace, execution_id),
            ).fetchone()
            return None if row is None else self._result_from_row(row)

    def finalize(
        self,
        result: AIExecutionResult,
        *,
        expected_execution_version: int,
        now: datetime | None = None,
    ) -> AIExecution:
        if not isinstance(result, AIExecutionResult):
            raise TypeError("result must be AIExecutionResult")
        instant = _utc(now or result.completed_at)
        terminal_state = {
            "completed": ExecutionState.COMPLETED,
            "degraded": ExecutionState.COMPLETED,
            "failed": ExecutionState.FAILED,
            "cancelled": ExecutionState.CANCELLED,
        }[result.status]

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(result.execution_id)
                if current.operation_id != result.operation_id:
                    raise ExecutionRepositoryConflict(
                        "result operation does not match execution"
                    )
                existing = self.result(result.execution_id)
                if existing is not None:
                    if existing.as_dict() != result.as_dict():
                        raise ExecutionRepositoryConflict(
                            "terminal execution result already differs"
                        )
                    self._connection.execute("COMMIT")
                    return current
                if current.version != expected_execution_version:
                    raise ExecutionRepositoryConflict(
                        "execution version changed before finalization"
                    )

                if terminal_state in {
                    ExecutionState.FAILED,
                    ExecutionState.CANCELLED,
                }:
                    # Failure/cancellation must remain possible from wait states
                    # where FINALIZING is intentionally not an allowed hop.
                    target = current.transition(terminal_state, now=instant)
                else:
                    target = current.transition(
                        ExecutionState.FINALIZING,
                        now=instant,
                    )
                    target = target.transition(
                        ExecutionState.COMPLETED,
                        now=instant,
                    )
                next_state = target.state
                next_version = target.version

                self._connection.execute(
                    """
                    INSERT INTO ai_execution_result(
                        namespace, execution_id, result_json, completed_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        result.execution_id,
                        _json_dump(result.as_dict()),
                        result.completed_at.isoformat(),
                    ),
                )

                outbox_id = _outbox_id(
                    self.namespace,
                    result.execution_id,
                    next_version,
                    "terminal",
                )
                payload = {
                    "operation_id": result.operation_id,
                    "execution_id": result.execution_id,
                    "status": result.status,
                    "result_ref": f"execution-result:{result.execution_id}",
                    "stream_terminal_event": result.stream_terminal_event,
                    "verification": result.verification,
                }
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_outbox(
                        namespace, outbox_id, execution_id, execution_version,
                        event_type, payload_json, created_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        self.namespace,
                        outbox_id,
                        result.execution_id,
                        next_version,
                        "execution." + result.status,
                        _json_dump(payload),
                        instant.isoformat(),
                    ),
                )
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET state = ?, version = ?, updated_at = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        next_state.value,
                        next_version,
                        instant.isoformat(),
                        self.namespace,
                        result.execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict(
                        "execution changed during atomic finalization"
                    )
                self._connection.execute("COMMIT")
                return AIExecution(
                    request=current.request,
                    state=next_state,
                    version=next_version,
                    latest_turn_index=current.latest_turn_index,
                    checkpoint_version=current.checkpoint_version,
                    cancellation_requested=current.cancellation_requested,
                    updated_at=instant,
                )
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict(
                    "execution finalization conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def pending_outbox(
        self,
        *,
        execution_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[ExecutionOutboxEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            if execution_id is None:
                rows = self._connection.execute(
                    """
                    SELECT * FROM ai_execution_outbox
                    WHERE namespace = ? AND published_at IS NULL
                    ORDER BY created_at ASC, execution_id ASC, execution_version ASC
                    LIMIT ?
                    """,
                    (self.namespace, limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM ai_execution_outbox
                    WHERE namespace = ? AND execution_id = ? AND published_at IS NULL
                    ORDER BY execution_version ASC
                    LIMIT ?
                    """,
                    (self.namespace, execution_id, limit),
                ).fetchall()
            return tuple(self._outbox_from_row(row) for row in rows)

    def acknowledge_outbox(
        self,
        outbox_id: str,
        *,
        published_at: datetime | None = None,
    ) -> ExecutionOutboxEvent:
        instant = _utc(published_at)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM ai_execution_outbox
                    WHERE namespace = ? AND outbox_id = ?
                    """,
                    (self.namespace, outbox_id),
                ).fetchone()
                if row is None:
                    raise ExecutionRepositoryError("unknown execution outbox event")
                current = self._outbox_from_row(row)
                if current.published_at is not None:
                    self._connection.execute("COMMIT")
                    return current
                self._connection.execute(
                    """
                    UPDATE ai_execution_outbox
                    SET published_at = ?
                    WHERE namespace = ? AND outbox_id = ?
                    """,
                    (instant.isoformat(), self.namespace, outbox_id),
                )
                self._connection.execute("COMMIT")
                return ExecutionOutboxEvent(
                    outbox_id=current.outbox_id,
                    execution_id=current.execution_id,
                    execution_version=current.execution_version,
                    event_type=current.event_type,
                    payload=dict(current.payload),
                    created_at=current.created_at,
                    published_at=instant,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def recoverable(self) -> tuple[AIExecution, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM ai_execution_state
                WHERE namespace = ?
                  AND state NOT IN (?, ?, ?)
                ORDER BY updated_at ASC, execution_id ASC
                """,
                (
                    self.namespace,
                    ExecutionState.COMPLETED.value,
                    ExecutionState.FAILED.value,
                    ExecutionState.CANCELLED.value,
                ),
            ).fetchall()
            return tuple(self._execution_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "ExecutionOutboxEvent",
    "ExecutionRepositoryConflict",
    "ExecutionRepositoryCorruption",
    "ExecutionRepositoryError",
    "SQLiteExecutionRepository",
]
