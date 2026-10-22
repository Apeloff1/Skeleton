"""Durable cognitive-execution repository and finalization outbox.

The execution repository is authoritative for execution state, turn lineage,
checkpoints, terminal results, and retry-stable finalization events. SQLite is
the deterministic reference implementation; higher-scale stores must preserve
the same compare-and-set and transactional semantics.
"""

from __future__ import annotations

import json
import hashlib
import base64
import binascii
import sqlite3
import threading
from dataclasses import dataclass
from skeleton.compat.datetime_utc import UTC
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.ai_execution import (
    AgentTurn,
    AIExecution,
    AIExecutionRequest,
    AIExecutionResult,
    ExecutionCheckpoint,
    ExecutionFinalizationIntent,
    ExecutionState,
    execution_payload_digest,
)
from skeleton.contracts.verification import VerificationReceipt
from skeleton.contracts import runtime_learning as learning


class ExecutionRepositoryError(RuntimeError):
    """Base durable execution repository failure."""


class ExecutionRepositoryConflict(ExecutionRepositoryError):
    """Execution identity/version/lineage conflict."""


class ExecutionRepositoryCorruption(ExecutionRepositoryError):
    """Persisted execution state cannot be interpreted safely."""


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(UTC) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ExecutionRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(UTC)


def _parse_time(raw: object, field: str) -> datetime:
    if not isinstance(raw, str):
        raise ExecutionRepositoryCorruption(f"{field} must be ISO text")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ExecutionRepositoryCorruption(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionRepositoryCorruption(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


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
        self.path = str(path)
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript("""
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS ai_execution_coordinator_identity (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    namespace TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ai_execution_stream_event (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_key TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    PRIMARY KEY(namespace, execution_id, sequence),
                    UNIQUE(namespace, execution_id, event_key),
                    FOREIGN KEY(namespace, execution_id) REFERENCES ai_execution_state(namespace, execution_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_execution_state (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    identity_digest TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
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

                CREATE INDEX IF NOT EXISTS idx_ai_execution_recoverable_keyset
                ON ai_execution_state(namespace, updated_at, execution_id)
                WHERE state NOT IN ('completed', 'failed', 'cancelled');
                DROP INDEX IF EXISTS idx_ai_execution_active_keyset;
                CREATE INDEX IF NOT EXISTS idx_ai_execution_actionable_keyset
                ON ai_execution_state(namespace, updated_at, execution_id)
                WHERE state NOT IN ('completed', 'failed', 'cancelled')
                  AND (state NOT IN ('waiting_for_user', 'waiting_for_tool_authority') OR cancellation_requested = 1);

                CREATE TABLE IF NOT EXISTS ai_execution_turn (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    parent_turn_id TEXT,
                    turn_digest TEXT NOT NULL,
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
                    checkpoint_digest TEXT NOT NULL,
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
                    result_digest TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    learning_outcome_id TEXT,
                    learning_observation_digest TEXT,
                    learning_observed_at TEXT,
                    learning_trained INTEGER,
                    learning_status TEXT,
                    learning_checkpoint_version INTEGER,
                    learning_tenant_id TEXT,
                    learning_scope_id TEXT,
                    learning_partition_id TEXT,
                    learning_model_selection_digest TEXT,
                    learning_source_snapshot_digest TEXT,
                    learning_policy_version INTEGER,
                    learning_policy_digest TEXT,
                    PRIMARY KEY(namespace, execution_id),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_verification_receipt (
                    namespace TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    execution_id TEXT,
                    operation_id TEXT,
                    result_ref TEXT,
                    receipt_digest TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, receipt_id),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_ai_verification_receipt_claim
                ON ai_verification_receipt(namespace, claim_id, verified_at);

                CREATE INDEX IF NOT EXISTS idx_ai_verification_receipt_execution
                ON ai_verification_receipt(namespace, execution_id, verified_at);

                CREATE TABLE IF NOT EXISTS ai_execution_finalization_intent (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    expected_execution_version INTEGER NOT NULL,
                    intent_digest TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    staged_at TEXT NOT NULL,
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
                    payload_digest TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS ai_execution_learning_outcome (
                    namespace TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    outcome_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    partition_id TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    model_selection_digest TEXT NOT NULL,
                    source_snapshot_digest TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    result_digest TEXT NOT NULL,
                    observation_digest TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    trained INTEGER NOT NULL,
                    learning_status TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, execution_id),
                    UNIQUE(namespace, outcome_id),
                    FOREIGN KEY(namespace, execution_id)
                        REFERENCES ai_execution_state(namespace, execution_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_recent
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, observed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_replay
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, partition_id, observed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_source
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, partition_id, source_snapshot_digest);
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_accepted_replay
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, partition_id, observed_at DESC)
                WHERE trained = 1;
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_dataset
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, observed_at, execution_id);
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_partition_dataset
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, partition_id, observed_at, execution_id);
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_accepted_dataset
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, observed_at, execution_id) WHERE trained = 1;
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_accepted_partition_dataset
                ON ai_execution_learning_outcome(namespace, tenant_id, scope_id, partition_id, observed_at, execution_id) WHERE trained = 1;

                CREATE TABLE IF NOT EXISTS ai_execution_learning_state (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    partition_id TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    model_selection_digest TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state_digest TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_observed_at TEXT,
                    maintenance_at TEXT,
                    PRIMARY KEY(namespace, tenant_id, scope_id, partition_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_maintenance
                ON ai_execution_learning_state(namespace, tenant_id, scope_id, maintenance_at, updated_at);

                CREATE TABLE IF NOT EXISTS ai_execution_learning_policy (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    policy_digest TEXT NOT NULL,
                    policy_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, scope_id)
                );
                CREATE TABLE IF NOT EXISTS ai_execution_learning_totals (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    totals_digest TEXT NOT NULL,
                    totals_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, scope_id)
                );
                CREATE TABLE IF NOT EXISTS ai_execution_runtime_control_policy (
                    namespace TEXT NOT NULL PRIMARY KEY,
                    version INTEGER NOT NULL,
                    policy_digest TEXT NOT NULL,
                    policy_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_execution_runtime_control_event (
                    namespace TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    tenant_id TEXT,
                    actor_digest TEXT,
                    policy_digest TEXT NOT NULL,
                    previous_policy_digest TEXT NOT NULL,
                    learning_policy_digest TEXT,
                    changed_sections_json TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, version),
                    FOREIGN KEY(namespace)
                        REFERENCES ai_execution_runtime_control_policy(namespace)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_execution_runtime_control_history
                ON ai_execution_runtime_control_event(namespace, tenant_id, version DESC);
                CREATE TABLE IF NOT EXISTS ai_execution_learning_maintenance_receipt (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    binding_digest TEXT NOT NULL,
                    result_digest TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    acknowledgement_digest TEXT,
                    compacted_at TEXT,
                    PRIMARY KEY(namespace, tenant_id, scope_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS ai_execution_learning_retention_state (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    policy_limit INTEGER NOT NULL,
                    live_rows INTEGER NOT NULL,
                    overflow INTEGER NOT NULL,
                    pruned_rows INTEGER NOT NULL,
                    skipped_rows INTEGER NOT NULL,
                    last_deferred_reason TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, scope_id)
                );
                """)
            learning_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_learning_state)")
            }
            if "last_observed_at" not in learning_columns:
                self._connection.execute("ALTER TABLE ai_execution_learning_state ADD COLUMN last_observed_at TEXT")
            marker_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_result)")
            }
            for name, kind in (
                ("learning_outcome_id", "TEXT"),
                ("learning_observation_digest", "TEXT"),
                ("learning_observed_at", "TEXT"),
                ("learning_trained", "INTEGER"),
                ("learning_status", "TEXT"),
                ("learning_checkpoint_version", "INTEGER"),
                ("learning_tenant_id", "TEXT"),
                ("learning_scope_id", "TEXT"),
                ("learning_partition_id", "TEXT"),
                ("learning_model_selection_digest", "TEXT"),
                ("learning_source_snapshot_digest", "TEXT"),
                ("learning_policy_version", "INTEGER"),
                ("learning_policy_digest", "TEXT"),
            ):
                if name not in marker_columns:
                    self._connection.execute(f"ALTER TABLE ai_execution_result ADD COLUMN {name} {kind}")
            receipt_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_learning_maintenance_receipt)")
            }
            for name in ("acknowledged_at", "acknowledgement_digest", "compacted_at"):
                if name not in receipt_columns:
                    self._connection.execute(f"ALTER TABLE ai_execution_learning_maintenance_receipt ADD COLUMN {name} TEXT")
            self._connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_execution_learning_marker "
                "ON ai_execution_result(namespace, learning_outcome_id) WHERE learning_outcome_id IS NOT NULL"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_marker_source "
                "ON ai_execution_result(namespace, learning_tenant_id, learning_scope_id, learning_partition_id, learning_source_snapshot_digest) "
                "WHERE learning_outcome_id IS NOT NULL"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_marker_recent "
                "ON ai_execution_result(namespace, learning_tenant_id, learning_scope_id, learning_partition_id, learning_observed_at DESC) "
                "WHERE learning_outcome_id IS NOT NULL"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_marker_replay "
                "ON ai_execution_result(namespace, learning_tenant_id, learning_scope_id, learning_partition_id, learning_observed_at DESC) "
                "WHERE learning_outcome_id IS NOT NULL AND learning_trained = 1"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_receipt_retention "
                "ON ai_execution_learning_maintenance_receipt(namespace, tenant_id, scope_id, compacted_at, acknowledged_at, idempotency_key)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_execution_learning_observed "
                "ON ai_execution_learning_state(namespace, tenant_id, scope_id, last_observed_at)"
            )
            state_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_state)")
            }
            if "state_digest" not in state_columns:
                self._connection.execute("ALTER TABLE ai_execution_state " "ADD COLUMN state_digest TEXT")
            for row in self._connection.execute("""
                SELECT * FROM ai_execution_state
                WHERE state_digest IS NULL OR state_digest = ''
                """).fetchall():
                request_payload = _json_object(
                    row["request_json"],
                    "request_json",
                )
                request = self._request_from_dict(request_payload)
                if request.identity_digest != row["identity_digest"]:
                    raise ExecutionRepositoryCorruption("persisted execution identity digest mismatch")
                execution = AIExecution(
                    request=request,
                    state=ExecutionState(row["state"]),
                    version=int(row["version"]),
                    latest_turn_index=int(row["latest_turn_index"]),
                    checkpoint_version=int(row["checkpoint_version"]),
                    cancellation_requested=bool(row["cancellation_requested"]),
                    updated_at=_parse_time(
                        row["updated_at"],
                        "updated_at",
                    ),
                )
                self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET state_digest = ?
                    WHERE namespace = ? AND execution_id = ?
                    """,
                    (
                        self._execution_state_digest(execution),
                        row["namespace"],
                        row["execution_id"],
                    ),
                )

            turn_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_turn)")
            }
            if "turn_digest" not in turn_columns:
                self._connection.execute("ALTER TABLE ai_execution_turn " "ADD COLUMN turn_digest TEXT")
            for row in self._connection.execute("""
                SELECT namespace, execution_id, turn_id, turn_json
                FROM ai_execution_turn
                WHERE turn_digest IS NULL OR turn_digest = ''
                """).fetchall():
                payload = _json_object(row["turn_json"], "turn_json")
                digest = execution_payload_digest(payload)
                self._connection.execute(
                    """
                    UPDATE ai_execution_turn
                    SET turn_digest = ?
                    WHERE namespace = ? AND execution_id = ? AND turn_id = ?
                    """,
                    (
                        digest,
                        row["namespace"],
                        row["execution_id"],
                        row["turn_id"],
                    ),
                )

            checkpoint_columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(ai_execution_checkpoint)")
            }
            if "checkpoint_digest" not in checkpoint_columns:
                self._connection.execute(
                    "ALTER TABLE ai_execution_checkpoint " "ADD COLUMN checkpoint_digest TEXT"
                )
            for row in self._connection.execute("""
                SELECT namespace, execution_id, checkpoint_version,
                       checkpoint_json
                FROM ai_execution_checkpoint
                WHERE checkpoint_digest IS NULL OR checkpoint_digest = ''
                """).fetchall():
                payload = _json_object(
                    row["checkpoint_json"],
                    "checkpoint_json",
                )
                digest = execution_payload_digest(payload)
                self._connection.execute(
                    """
                    UPDATE ai_execution_checkpoint
                    SET checkpoint_digest = ?
                    WHERE namespace = ? AND execution_id = ?
                      AND checkpoint_version = ?
                    """,
                    (
                        digest,
                        row["namespace"],
                        row["execution_id"],
                        row["checkpoint_version"],
                    ),
                )

            result_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_result)")
            }
            if "result_digest" not in result_columns:
                self._connection.execute("ALTER TABLE ai_execution_result " "ADD COLUMN result_digest TEXT")
            for row in self._connection.execute("""
                SELECT namespace, execution_id, result_json
                FROM ai_execution_result
                WHERE result_digest IS NULL OR result_digest = ''
                """).fetchall():
                payload = _json_object(row["result_json"], "result_json")
                result = self._result_from_payload(payload)
                digest = execution_payload_digest(result.as_dict())
                self._connection.execute(
                    """
                    UPDATE ai_execution_result
                    SET result_digest = ?
                    WHERE namespace = ? AND execution_id = ?
                    """,
                    (
                        digest,
                        row["namespace"],
                        row["execution_id"],
                    ),
                )

            outbox_columns = {
                str(row["name"]) for row in self._connection.execute("PRAGMA table_info(ai_execution_outbox)")
            }
            if "payload_digest" not in outbox_columns:
                self._connection.execute("ALTER TABLE ai_execution_outbox " "ADD COLUMN payload_digest TEXT")
            for row in self._connection.execute("""
                SELECT namespace, outbox_id, payload_json
                FROM ai_execution_outbox
                WHERE payload_digest IS NULL OR payload_digest = ''
                """).fetchall():
                payload = _json_object(row["payload_json"], "payload_json")
                digest = execution_payload_digest(payload)
                self._connection.execute(
                    """
                    UPDATE ai_execution_outbox
                    SET payload_digest = ?
                    WHERE namespace = ? AND outbox_id = ?
                    """,
                    (
                        digest,
                        row["namespace"],
                        row["outbox_id"],
                    ),
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

    @staticmethod
    def _execution_state_digest(execution: AIExecution) -> str:
        return execution_payload_digest(
            {
                "operation_id": execution.operation_id,
                "execution_id": execution.execution_id,
                "identity_digest": execution.request.identity_digest,
                "state": execution.state.value,
                "version": execution.version,
                "latest_turn_index": execution.latest_turn_index,
                "checkpoint_version": execution.checkpoint_version,
                "cancellation_requested": execution.cancellation_requested,
                "updated_at": execution.updated_at.isoformat(),
            }
        )

    def _execution_from_row(self, row: sqlite3.Row) -> AIExecution:
        try:
            request_payload = _json_object(row["request_json"], "request_json")
            request = self._request_from_dict(request_payload)
            if request.identity_digest != row["identity_digest"]:
                raise ExecutionRepositoryCorruption("persisted execution identity digest mismatch")
            if request.execution_id != row["execution_id"] or request.operation_id != row["operation_id"]:
                raise ExecutionRepositoryCorruption("persisted execution request identity mismatch")
            execution = AIExecution(
                request=request,
                state=ExecutionState(row["state"]),
                version=int(row["version"]),
                latest_turn_index=int(row["latest_turn_index"]),
                checkpoint_version=int(row["checkpoint_version"]),
                cancellation_requested=bool(row["cancellation_requested"]),
                updated_at=_parse_time(row["updated_at"], "updated_at"),
            )
            digest = self._execution_state_digest(execution)
            if digest != row["state_digest"]:
                raise ExecutionRepositoryCorruption("persisted execution state digest mismatch")
            return execution
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted execution violates contract") from exc

    @staticmethod
    def _turn_from_row(row: sqlite3.Row) -> AgentTurn:
        try:
            payload = _json_object(row["turn_json"], "turn_json")
            turn = AgentTurn(
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
            digest = execution_payload_digest(turn.as_dict())
            if digest != row["turn_digest"]:
                raise ExecutionRepositoryCorruption("persisted turn digest mismatch")
            return turn
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted turn violates contract") from exc

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row) -> ExecutionCheckpoint:
        try:
            payload = _json_object(row["checkpoint_json"], "checkpoint_json")
            checkpoint = ExecutionCheckpoint(
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
            digest = execution_payload_digest(checkpoint.as_dict())
            if digest != row["checkpoint_digest"]:
                raise ExecutionRepositoryCorruption("persisted checkpoint digest mismatch")
            return checkpoint
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted checkpoint violates contract") from exc

    @staticmethod
    def _result_from_payload(payload: dict[str, Any]) -> AIExecutionResult:
        return AIExecutionResult(
            operation_id=payload["operation_id"],
            execution_id=payload["execution_id"],
            status=payload["status"],
            final_output=payload.get("final_output"),
            verification=payload.get("verification"),
            verification_receipt=payload.get("verification_receipt"),
            evidence_refs=tuple(payload.get("evidence_refs") or ()),
            route_receipts=tuple(payload.get("route_receipts") or ()),
            provider_receipts=tuple(payload.get("provider_receipts") or ()),
            tool_receipts=tuple(payload.get("tool_receipts") or ()),
            memory_refs=tuple(payload.get("memory_refs") or ()),
            artifact_refs=tuple(payload.get("artifact_refs") or ()),
            usage=payload.get("usage") or {},
            stream_terminal_event=payload.get("stream_terminal_event"),
            completed_at=_parse_time(payload["completed_at"], "completed_at"),
        )

    @classmethod
    def _result_from_row(cls, row: sqlite3.Row) -> AIExecutionResult:
        try:
            payload = _json_object(row["result_json"], "result_json")
            result = cls._result_from_payload(payload)
            digest = execution_payload_digest(result.as_dict())
            if digest != row["result_digest"]:
                raise ExecutionRepositoryCorruption("persisted result digest mismatch")
            return result
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted result violates contract") from exc

    @staticmethod
    def _verification_receipt_from_row(
        row: sqlite3.Row,
    ) -> VerificationReceipt:
        try:
            payload = _json_object(row["receipt_json"], "receipt_json")
            receipt = VerificationReceipt(
                receipt_id=payload["receipt_id"],
                claim_id=payload["claim_id"],
                claim_digest=payload["claim_digest"],
                tenant_id=payload["tenant_id"],
                operation_id=payload.get("operation_id"),
                execution_id=payload.get("execution_id"),
                turn_id=payload.get("turn_id"),
                result_ref=payload.get("result_ref"),
                outcome=payload["outcome"],
                policy_level=int(payload["policy_level"]),
                required_modes=tuple(payload.get("required_modes") or ()),
                policy_satisfied=bool(payload["policy_satisfied"]),
                check_id=payload.get("check_id"),
                verifier_id=payload["verifier_id"],
                verified_at=_parse_time(
                    payload["verified_at"],
                    "verified_at",
                ),
                supporting_evidence_ids=tuple(payload.get("supporting_evidence_ids") or ()),
                contradicting_evidence_ids=tuple(payload.get("contradicting_evidence_ids") or ()),
                rejected_evidence_ids=tuple(payload.get("rejected_evidence_ids") or ()),
                postcondition_observation_ids=tuple(payload.get("postcondition_observation_ids") or ()),
                independent=bool(payload.get("independent", False)),
                issues=tuple(payload.get("issues") or ()),
                schema_version=int(payload.get("schema_version", 1)),
            )
            if receipt.digest != row["receipt_digest"]:
                raise ExecutionRepositoryCorruption("persisted verification receipt digest mismatch")
            return receipt
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted verification receipt violates contract") from exc

    @classmethod
    def _intent_from_row(cls, row: sqlite3.Row) -> ExecutionFinalizationIntent:
        try:
            payload = _json_object(row["intent_json"], "intent_json")
            result_payload = payload.get("result")
            if not isinstance(result_payload, dict):
                raise ExecutionRepositoryCorruption("finalization intent result must be an object")
            intent = ExecutionFinalizationIntent(
                result=cls._result_from_payload(result_payload),
                expected_execution_version=int(payload["expected_execution_version"]),
                staged_at=_parse_time(payload["staged_at"], "staged_at"),
            )
            if intent.intent_digest != row["intent_digest"]:
                raise ExecutionRepositoryCorruption("persisted finalization intent digest mismatch")
            if payload.get("intent_digest") != intent.intent_digest:
                raise ExecutionRepositoryCorruption("finalization intent payload digest mismatch")
            return intent
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted finalization intent violates contract") from exc

    @staticmethod
    def _outbox_from_row(row: sqlite3.Row) -> ExecutionOutboxEvent:
        try:
            payload = _json_object(row["payload_json"], "payload_json")
            digest = execution_payload_digest(payload)
            if digest != row["payload_digest"]:
                raise ExecutionRepositoryCorruption("persisted outbox payload digest mismatch")
            return ExecutionOutboxEvent(
                outbox_id=row["outbox_id"],
                execution_id=row["execution_id"],
                execution_version=int(row["execution_version"]),
                event_type=row["event_type"],
                payload=payload,
                created_at=_parse_time(row["created_at"], "created_at"),
                published_at=(
                    None if row["published_at"] is None else _parse_time(row["published_at"], "published_at")
                ),
            )
        except ExecutionRepositoryCorruption:
            raise
        except Exception as exc:
            raise ExecutionRepositoryCorruption("persisted outbox event violates contract") from exc

    def append_stream_event(
        self,
        execution_id: str,
        event_key: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        expected_version: int | None = None,
        provisional: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Append a bounded immutable replay event under the execution authority."""
        if not isinstance(event_key, str) or not 1 <= len(event_key) <= 512:
            raise ExecutionRepositoryError("stream event identity is invalid")
        if type(provisional) is not bool or (
            expected_version is not None and (type(expected_version) is not int or expected_version < 1)
        ):
            raise ExecutionRepositoryError("stream publication fence/qualification is invalid")
        if (
            not isinstance(event_type, str)
            or not 1 <= len(event_type) <= 128
            or not isinstance(payload, dict)
        ):
            raise ExecutionRepositoryError("stream event type/payload is invalid")
        value = {
            "execution_id": execution_id,
            "type": event_type,
            "payload": payload,
            "provisional": provisional,
        }
        encoded_payload = _json_dump(value)
        if len(encoded_payload.encode("utf-8")) > 262144:
            raise ExecutionRepositoryError("stream event exceeds byte limit")
        content_digest = execution_payload_digest(value)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(execution_id)
                if expected_version is not None and current.version != expected_version:
                    raise ExecutionRepositoryConflict("execution version changed before stream publication")
                existing = self._connection.execute(
                    "SELECT event_digest,CASE WHEN length(CAST(event_json AS BLOB))<=262144 THEN event_json ELSE NULL END AS event_json FROM ai_execution_stream_event "
                    "WHERE namespace=? AND execution_id=? AND event_key=?",
                    (self.namespace, execution_id, event_key),
                ).fetchone()
                if existing is not None:
                    if existing["event_json"] is None:
                        raise ExecutionRepositoryCorruption("existing stream event exceeds byte bounds")
                    event = _json_object(existing["event_json"], "stream_event")
                    original = {key: event[key] for key in value}
                    if execution_payload_digest(original) != content_digest or original != value:
                        raise ExecutionRepositoryConflict(
                            "stream event identity was reused for different content"
                        )
                    if execution_payload_digest(event) != existing["event_digest"]:
                        raise ExecutionRepositoryCorruption("stream event digest mismatch")
                    self._connection.commit()
                    return event
                if provisional and (current.cancellation_requested or current.terminal):
                    raise ExecutionRepositoryConflict(
                        "provisional output cannot publish after cancellation or finalization"
                    )
                aggregate = self._connection.execute(
                    "SELECT COALESCE(MAX(sequence),0),COUNT(*),COALESCE(SUM(size_bytes),0) "
                    "FROM ai_execution_stream_event WHERE namespace=? AND execution_id=?",
                    (self.namespace, execution_id),
                ).fetchone()
                sequence = int(aggregate[0]) + 1
                event = {
                    **value,
                    "event_id": f"execution-stream:{execution_id}:{sequence}",
                    "sequence": sequence,
                    "created_at": _utc(now).isoformat(),
                }
                encoded = _json_dump(event)
                size = len(encoded.encode("utf-8"))
                if size > 262144 or int(aggregate[1]) >= 65536 or int(aggregate[2]) + size > 33554432:
                    raise ExecutionRepositoryError("execution stream retention bounds exceeded")
                self._connection.execute(
                    "INSERT INTO ai_execution_stream_event VALUES (?,?,?,?,?,?,?)",
                    (
                        self.namespace,
                        execution_id,
                        sequence,
                        event_key,
                        execution_payload_digest(event),
                        encoded,
                        size,
                    ),
                )
                self._connection.commit()
                return event
            except BaseException:
                self._connection.rollback()
                raise

    def stream_events(
        self, execution_id: str, *, after_sequence: int = 0, limit: int = 256
    ) -> dict[str, Any]:
        """Read exact immutable event pages; the cursor acknowledges the last event."""
        if (
            type(after_sequence) is not int
            or not 0 <= after_sequence <= 2**63 - 1
            or type(limit) is not int
            or not 1 <= limit <= 1024
        ):
            raise ExecutionRepositoryError("stream cursor/page bounds are invalid")
        with self._lock:
            self.get(execution_id)
            rows = self._connection.execute(
                "SELECT sequence,event_digest,CASE WHEN length(CAST(event_json AS BLOB))<=262144 THEN event_json ELSE NULL END AS event_json,size_bytes FROM ai_execution_stream_event "
                "WHERE namespace=? AND execution_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (self.namespace, execution_id, after_sequence, limit),
            ).fetchall()
            last = self._connection.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM ai_execution_stream_event WHERE namespace=? AND execution_id=?",
                (self.namespace, execution_id),
            ).fetchone()[0]
        if after_sequence > last:
            raise ExecutionRepositoryConflict("stream cursor is beyond durable history")
        events = []
        expected = after_sequence + 1
        for row in rows:
            if (
                row["event_json"] is None
                or row["size_bytes"] > 262144
                or len(row["event_json"].encode("utf-8")) != row["size_bytes"]
            ):
                raise ExecutionRepositoryCorruption("stream event exceeds declared size")
            event = _json_object(row["event_json"], "stream_event")
            if (
                event.get("sequence") != expected
                or row["sequence"] != expected
                or execution_payload_digest(event) != row["event_digest"]
                or event.get("execution_id") != execution_id
                or type(event.get("sequence")) is not int
                or event.get("event_id") != f"execution-stream:{execution_id}:{expected}"
                or type(event.get("provisional")) is not bool
                or not isinstance(event.get("payload"), dict)
                or not isinstance(event.get("type"), str)
            ):
                raise ExecutionRepositoryCorruption("stream history identity/gap mismatch")
            events.append(event)
            expected += 1
        return {
            "execution_id": execution_id,
            "events": events,
            "stream_schema_version": 1,
            "last_sequence": expected - 1,
            "next_sequence": expected,
            "has_more": expected - 1 < last,
            "latest_sequence": last,
        }

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

                initial = AIExecution(
                    request=request,
                    updated_at=instant,
                )
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_state(
                        namespace, execution_id, operation_id, identity_digest,
                        state_digest, request_json, state, version,
                        latest_turn_index, checkpoint_version,
                        cancellation_requested, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, -1, 0, 0, ?)
                    """,
                    (
                        self.namespace,
                        request.execution_id,
                        request.operation_id,
                        request.identity_digest,
                        self._execution_state_digest(initial),
                        _json_dump(request.as_dict()),
                        ExecutionState.CREATED.value,
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return initial
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict("execution durable identity conflict") from exc
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
                    raise ExecutionRepositoryConflict("execution version changed before transition")
                updated = current.transition(target, now=instant)
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET state = ?, version = ?, updated_at = ?,
                        state_digest = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        updated.state.value,
                        updated.version,
                        instant.isoformat(),
                        self._execution_state_digest(updated),
                        self.namespace,
                        execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict("execution version changed during transition")
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
                    raise ExecutionRepositoryConflict("execution version changed before cancellation request")
                if current.terminal:
                    self._connection.execute("COMMIT")
                    return current
                updated = AIExecution(
                    request=current.request,
                    state=current.state,
                    version=current.version + 1,
                    latest_turn_index=current.latest_turn_index,
                    checkpoint_version=current.checkpoint_version,
                    cancellation_requested=True,
                    updated_at=instant,
                )
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET cancellation_requested = 1, version = ?,
                        updated_at = ?, state_digest = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        updated.version,
                        instant.isoformat(),
                        self._execution_state_digest(updated),
                        self.namespace,
                        execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict("execution version changed during cancellation request")
                self._connection.execute("COMMIT")
                return updated
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
                    raise ExecutionRepositoryConflict("turn operation does not match execution")
                if current.version != expected_execution_version:
                    raise ExecutionRepositoryConflict("execution version changed before turn append")
                expected_turn_index = current.latest_turn_index + 1
                if turn.turn_index != expected_turn_index:
                    raise ExecutionRepositoryConflict("turn_index must strictly increase")
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
                        raise ExecutionRepositoryConflict("turn parent does not match immutable lineage")
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_turn(
                        namespace, execution_id, turn_id, turn_index,
                        parent_turn_id, turn_digest, turn_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        turn.execution_id,
                        turn.turn_id,
                        turn.turn_index,
                        turn.parent_turn_id,
                        execution_payload_digest(turn.as_dict()),
                        _json_dump(turn.as_dict()),
                    ),
                )
                next_version = current.version + 1
                updated = AIExecution(
                    request=current.request,
                    state=current.state,
                    version=next_version,
                    latest_turn_index=turn.turn_index,
                    checkpoint_version=current.checkpoint_version,
                    cancellation_requested=current.cancellation_requested,
                    updated_at=instant,
                )
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET latest_turn_index = ?, version = ?, updated_at = ?,
                        state_digest = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        turn.turn_index,
                        next_version,
                        instant.isoformat(),
                        self._execution_state_digest(updated),
                        self.namespace,
                        turn.execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict("execution changed during turn append")
                self._connection.execute("COMMIT")
                return updated
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict("turn identity or index already exists") from exc
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
                    raise ExecutionRepositoryConflict("execution version changed before checkpoint")
                if current.checkpoint_version != expected_checkpoint_version:
                    raise ExecutionRepositoryConflict("checkpoint version changed before compare-and-set")
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
                        checkpoint_digest, checkpoint_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        execution_id,
                        next_checkpoint_version,
                        execution_payload_digest(checkpoint.as_dict()),
                        _json_dump(checkpoint.as_dict()),
                        instant.isoformat(),
                    ),
                )
                updated = AIExecution(
                    request=current.request,
                    state=current.state,
                    version=next_execution_version,
                    latest_turn_index=current.latest_turn_index,
                    checkpoint_version=next_checkpoint_version,
                    cancellation_requested=current.cancellation_requested,
                    updated_at=instant,
                )
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET checkpoint_version = ?, version = ?, updated_at = ?,
                        state_digest = ?
                    WHERE namespace = ? AND execution_id = ?
                      AND version = ? AND checkpoint_version = ?
                    """,
                    (
                        next_checkpoint_version,
                        next_execution_version,
                        instant.isoformat(),
                        self._execution_state_digest(updated),
                        self.namespace,
                        execution_id,
                        current.version,
                        current.checkpoint_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict("execution changed during checkpoint compare-and-set")
                self._connection.execute("COMMIT")
                return checkpoint
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict("checkpoint identity conflict") from exc
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

    def remember_verification_receipt(
        self,
        receipt: VerificationReceipt,
    ) -> VerificationReceipt:
        if not isinstance(receipt, VerificationReceipt):
            raise TypeError("receipt must be VerificationReceipt")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM ai_verification_receipt
                    WHERE namespace = ? AND receipt_id = ?
                    """,
                    (self.namespace, receipt.receipt_id),
                ).fetchone()
                if row is not None:
                    existing = self._verification_receipt_from_row(row)
                    if existing.as_dict() != receipt.as_dict():
                        raise ExecutionRepositoryConflict("verification receipt identity already differs")
                    self._connection.execute("COMMIT")
                    return existing

                if receipt.execution_id is not None:
                    execution_row = self._connection.execute(
                        """
                        SELECT execution_id FROM ai_execution_state
                        WHERE namespace = ? AND execution_id = ?
                        """,
                        (self.namespace, receipt.execution_id),
                    ).fetchone()
                    if execution_row is None:
                        raise ExecutionRepositoryConflict("verification receipt execution is unknown")

                self._connection.execute(
                    """
                    INSERT INTO ai_verification_receipt(
                        namespace, receipt_id, claim_id, execution_id,
                        operation_id, result_ref, receipt_digest,
                        receipt_json, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        receipt.receipt_id,
                        receipt.claim_id,
                        receipt.execution_id,
                        receipt.operation_id,
                        receipt.result_ref,
                        receipt.digest,
                        _json_dump(receipt.as_dict()),
                        receipt.verified_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return receipt
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict("verification receipt identity conflict") from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def verification_receipt(
        self,
        receipt_id: str,
    ) -> VerificationReceipt | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM ai_verification_receipt
                WHERE namespace = ? AND receipt_id = ?
                """,
                (self.namespace, str(receipt_id)),
            ).fetchone()
            return None if row is None else self._verification_receipt_from_row(row)

    def verification_receipts_for_execution(
        self,
        execution_id: str,
    ) -> tuple[VerificationReceipt, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM ai_verification_receipt
                WHERE namespace = ? AND execution_id = ?
                ORDER BY verified_at ASC, receipt_id ASC
                """,
                (self.namespace, str(execution_id)),
            ).fetchall()
            return tuple(self._verification_receipt_from_row(row) for row in rows)

    def verification_receipts_for_claim(
        self,
        claim_id: str,
    ) -> tuple[VerificationReceipt, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM ai_verification_receipt
                WHERE namespace = ? AND claim_id = ?
                ORDER BY verified_at ASC, receipt_id ASC
                """,
                (self.namespace, str(claim_id)),
            ).fetchall()
            return tuple(self._verification_receipt_from_row(row) for row in rows)

    def finalization_intent(
        self,
        execution_id: str,
    ) -> ExecutionFinalizationIntent | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM ai_execution_finalization_intent
                WHERE namespace = ? AND execution_id = ?
                """,
                (self.namespace, execution_id),
            ).fetchone()
            return None if row is None else self._intent_from_row(row)

    def stage_finalization(
        self,
        result: AIExecutionResult,
        *,
        expected_execution_version: int,
        now: datetime | None = None,
    ) -> ExecutionFinalizationIntent:
        if not isinstance(result, AIExecutionResult):
            raise TypeError("result must be AIExecutionResult")
        instant = _utc(now or result.completed_at)
        intent = ExecutionFinalizationIntent(
            result=result,
            expected_execution_version=expected_execution_version,
            staged_at=instant,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(result.execution_id)
                if current.operation_id != result.operation_id:
                    raise ExecutionRepositoryConflict(
                        "finalization intent operation does not match execution"
                    )
                existing_result = self.result(result.execution_id)
                if existing_result is not None:
                    if existing_result.as_dict() != result.as_dict():
                        raise ExecutionRepositoryConflict("terminal execution result already differs")
                    self._connection.execute("COMMIT")
                    return intent
                if current.version != expected_execution_version:
                    raise ExecutionRepositoryConflict("execution version changed before finalization staging")
                row = self._connection.execute(
                    """
                    SELECT * FROM ai_execution_finalization_intent
                    WHERE namespace = ? AND execution_id = ?
                    """,
                    (self.namespace, result.execution_id),
                ).fetchone()
                if row is not None:
                    existing = self._intent_from_row(row)
                    if existing.intent_digest != intent.intent_digest:
                        raise ExecutionRepositoryConflict("staged finalization intent already differs")
                    self._connection.execute("COMMIT")
                    return existing
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_finalization_intent(
                        namespace, execution_id, expected_execution_version,
                        intent_digest, intent_json, staged_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        result.execution_id,
                        expected_execution_version,
                        intent.intent_digest,
                        _json_dump(intent.as_dict()),
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return intent
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict("finalization intent identity conflict") from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def finalize_staged(
        self,
        execution_id: str,
        *,
        now: datetime | None = None,
    ) -> AIExecution:
        intent = self.finalization_intent(execution_id)
        if intent is None:
            existing = self.result(execution_id)
            if existing is not None:
                return self.get(execution_id)
            raise ExecutionRepositoryError("execution has no staged finalization intent")
        return self.finalize(
            intent.result,
            expected_execution_version=intent.expected_execution_version,
            now=now,
        )

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
                    raise ExecutionRepositoryConflict("result operation does not match execution")
                existing = self.result(result.execution_id)
                if existing is not None:
                    if existing.as_dict() != result.as_dict():
                        raise ExecutionRepositoryConflict("terminal execution result already differs")
                    self._record_runtime_outcome_locked(current, existing, instant)
                    self._connection.execute(
                        """
                        DELETE FROM ai_execution_finalization_intent
                        WHERE namespace = ? AND execution_id = ?
                        """,
                        (self.namespace, result.execution_id),
                    )
                    self._connection.execute("COMMIT")
                    return current
                if current.version != expected_execution_version:
                    raise ExecutionRepositoryConflict("execution version changed before finalization")

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
                updated = AIExecution(
                    request=current.request,
                    state=next_state,
                    version=next_version,
                    latest_turn_index=current.latest_turn_index,
                    checkpoint_version=current.checkpoint_version,
                    cancellation_requested=current.cancellation_requested,
                    updated_at=instant,
                )

                self._connection.execute(
                    """
                    INSERT INTO ai_execution_result(
                        namespace, execution_id, result_digest,
                        result_json, completed_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        result.execution_id,
                        execution_payload_digest(result.as_dict()),
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
                    "verification_receipt": result.verification_receipt,
                    "evidence_refs": list(result.evidence_refs),
                    "route_receipts": list(result.route_receipts),
                    "provider_receipts": list(result.provider_receipts),
                    "tool_receipts": list(result.tool_receipts),
                    "memory_refs": list(result.memory_refs),
                    "artifact_refs": list(result.artifact_refs),
                    "usage": dict(result.usage),
                }
                self._connection.execute(
                    """
                    INSERT INTO ai_execution_outbox(
                        namespace, outbox_id, execution_id, execution_version,
                        event_type, payload_digest, payload_json,
                        created_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        self.namespace,
                        outbox_id,
                        result.execution_id,
                        next_version,
                        "execution." + result.status,
                        execution_payload_digest(payload),
                        _json_dump(payload),
                        instant.isoformat(),
                    ),
                )
                cursor = self._connection.execute(
                    """
                    UPDATE ai_execution_state
                    SET state = ?, version = ?, updated_at = ?,
                        state_digest = ?
                    WHERE namespace = ? AND execution_id = ? AND version = ?
                    """,
                    (
                        next_state.value,
                        next_version,
                        instant.isoformat(),
                        self._execution_state_digest(updated),
                        self.namespace,
                        result.execution_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionRepositoryConflict("execution changed during atomic finalization")
                # Feedback and the actual terminal result share one commit. A
                # retry cannot lose an outcome or train it for a second time.
                self._record_runtime_outcome_locked(updated, result, instant)
                self._connection.execute(
                    """
                    DELETE FROM ai_execution_finalization_intent
                    WHERE namespace = ? AND execution_id = ?
                    """,
                    (self.namespace, result.execution_id),
                )
                self._connection.execute("COMMIT")
                return updated
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryConflict("execution finalization conflict") from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _learning_scope(tenant_id: str, scope_id: str) -> tuple[str, str]:
        try:
            return learning.identifier(tenant_id, "tenant_id", maximum=512), learning.identifier(scope_id, "scope_id")
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryError(str(exc)) from exc

    def _learning_policy_locked(self, tenant_id: str, scope_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            """SELECT * FROM ai_execution_learning_policy
               WHERE namespace = ? AND tenant_id = ? AND scope_id = ?""",
            (self.namespace, tenant_id, scope_id),
        ).fetchone()
        if row is None:
            return {"version": 1, "policy": learning.normalize_policy()}
        payload = _json_object(row["policy_json"], "learning policy")
        if learning.digest(payload) != row["policy_digest"]:
            raise ExecutionRepositoryCorruption("learning policy digest differs")
        try:
            policy = learning.normalize_policy(payload)
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryCorruption("learning policy is invalid") from exc
        return {"version": int(row["version"]), "policy": policy}

    def _write_learning_policy_locked(
        self, tenant_id: str, scope_id: str, policy: dict[str, Any], version: int, instant: datetime
    ) -> None:
        self._connection.execute(
            """INSERT INTO ai_execution_learning_policy(
                   namespace, tenant_id, scope_id, version, policy_digest, policy_json, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(namespace, tenant_id, scope_id) DO UPDATE SET
                   version = excluded.version, policy_digest = excluded.policy_digest,
                   policy_json = excluded.policy_json, updated_at = excluded.updated_at""",
            (self.namespace, tenant_id, scope_id, version, learning.digest(policy), _json_dump(policy), instant.isoformat()),
        )

    def set_runtime_learning_policy(
        self,
        *,
        tenant_id: str,
        scope_id: str = "tenant",
        policy: dict[str, Any],
        expected_version: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """CAS operator policy. Authentication remains the API owner's concern."""
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise ExecutionRepositoryError("expected learning policy version must be positive")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._learning_policy_locked(tenant_id, scope_id)
                if current["version"] != expected_version:
                    raise ExecutionRepositoryConflict("runtime learning policy version changed")
                if not isinstance(policy, dict):
                    raise ExecutionRepositoryError("learning policy must be an object")
                try:
                    merged = learning.normalize_policy({**current["policy"], **policy})
                except learning.RuntimeLearningError as exc:
                    raise ExecutionRepositoryError(str(exc)) from exc
                version = expected_version + 1
                self._write_learning_policy_locked(tenant_id, scope_id, merged, version, instant)
                self._connection.execute("COMMIT")
                return {"version": version, "policy": merged}
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def claim_coordinator_namespace(self) -> dict[str, Any]:
        """Pin a coordinated execution file to one namespace across restarts.

        Standalone repositories remain namespace-capable. The engine calls
        this explicit claim after obtaining its file lock, before activation.
        """
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT namespace FROM ai_execution_coordinator_identity WHERE singleton = 1"
                ).fetchone()
                if existing is not None:
                    if existing["namespace"] != self.namespace:
                        raise ExecutionRepositoryConflict("execution database is pinned to another coordinator namespace")
                    self._connection.execute("COMMIT")
                    return {"namespace": self.namespace, "claimed": True, "already_claimed": True}
                # Two index range probes avoid walking a large history that
                # already belongs entirely to the requested namespace.
                other = self._connection.execute(
                    "SELECT 1 FROM ai_execution_state WHERE namespace < ? LIMIT 1", (self.namespace,)
                ).fetchone()
                if other is None:
                    other = self._connection.execute(
                        "SELECT 1 FROM ai_execution_state WHERE namespace > ? LIMIT 1", (self.namespace,)
                    ).fetchone()
                if other is not None:
                    raise ExecutionRepositoryConflict("execution database contains another coordinator namespace")
                self._connection.execute(
                    "INSERT INTO ai_execution_coordinator_identity(singleton, namespace) VALUES (1, ?)",
                    (self.namespace,),
                )
                self._connection.execute("COMMIT")
                return {"namespace": self.namespace, "claimed": True, "already_claimed": False}
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def runtime_control_policy(self) -> dict[str, Any]:
        """Read the namespace's one durable host-control policy/version."""
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM ai_execution_runtime_control_policy WHERE namespace = ?", (self.namespace,)
            ).fetchone()
            if row is None:
                return {"version": 1, "policy": {}}
            payload = _json_object(row["policy_json"], "runtime control policy")
            if learning.digest(payload) != row["policy_digest"]:
                raise ExecutionRepositoryCorruption("runtime control policy digest differs")
            return {"version": int(row["version"]), "policy": payload}

    def _write_runtime_control_policy_locked(self, policy: dict[str, Any], version: int, instant: datetime) -> None:
        self._connection.execute(
            """INSERT INTO ai_execution_runtime_control_policy(
                   namespace, version, policy_digest, policy_json, updated_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(namespace) DO UPDATE SET version = excluded.version,
                   policy_digest = excluded.policy_digest, policy_json = excluded.policy_json,
                   updated_at = excluded.updated_at""",
            (self.namespace, version, learning.digest(policy), _json_dump(policy), instant.isoformat()),
        )

    def _append_runtime_control_event_locked(
        self, *, tenant_id: str | None, actor_id: str | None, version: int,
        policy: dict[str, Any], previous_policy: dict[str, Any], changed_sections: list[str],
        learning_policy_digest: str | None, instant: datetime,
        learning_checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        receipt = {
            "schema_version": "skeleton.runtime.control.event.v1", "tenant_id": tenant_id, "version": version,
            "actor_digest": None if actor_id is None else learning.digest({
                "namespace": self.namespace, "tenant_id": tenant_id, "actor_id": actor_id,
            }),
            "policy_digest": learning.digest(policy), "previous_policy_digest": learning.digest(previous_policy),
            "learning_policy_digest": learning_policy_digest, "changed_sections": changed_sections,
            "updated_at": instant.isoformat(),
        }
        if learning_checkpoint is not None:
            receipt["learning_checkpoint"] = learning_checkpoint
        receipt_digest = learning.digest(receipt)
        if len(_json_dump(receipt).encode()) > 4096:
            raise ExecutionRepositoryError("runtime control receipt exceeds its storage bound")
        self._connection.execute(
            """INSERT INTO ai_execution_runtime_control_event(
                   namespace, version, tenant_id, actor_digest, policy_digest, previous_policy_digest,
                   learning_policy_digest, changed_sections_json, receipt_digest, receipt_json, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.namespace, version, tenant_id, receipt["actor_digest"], receipt["policy_digest"],
             receipt["previous_policy_digest"], learning_policy_digest, _json_dump(changed_sections),
             receipt_digest, _json_dump(receipt), instant.isoformat()),
        )
        return {**receipt, "receipt_digest": receipt_digest}

    def set_runtime_control_policy(
        self,
        policy: dict[str, Any],
        expected_version: int,
        *,
        tenant_id: str | None = None,
        actor_id: str | None = None,
        scope_id: str = "tenant",
        learning_policy: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically CAS host controls and optional tenant learning settings.

        The host controller validates its own whitelist before this persistence
        seam. No serving controls become active through this repository alone.
        """
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise ExecutionRepositoryError("expected runtime control version must be positive")
        if not isinstance(policy, dict) or len(_json_dump(policy).encode()) > 32 * 1024:
            raise ExecutionRepositoryError("runtime control policy must be a bounded object")
        if tenant_id is not None:
            tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if actor_id is not None:
            try:
                actor_id = learning.identifier(actor_id, "actor_id", maximum=512)
            except learning.RuntimeLearningError as exc:
                raise ExecutionRepositoryError(str(exc)) from exc
        if learning_policy is not None:
            if tenant_id is None:
                raise ExecutionRepositoryError("tenant_id is required for learning policy")
            if not isinstance(learning_policy, dict):
                raise ExecutionRepositoryError("learning policy must be an object")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.runtime_control_policy()
                if current["version"] != expected_version:
                    raise ExecutionRepositoryConflict("runtime control policy version changed")
                learning_version = None
                learning_policy_digest = None
                changed_sections = []
                if policy != current["policy"]:
                    changed_sections.append("global_policy")
                if learning_policy is not None:
                    current_learning = self._learning_policy_locked(tenant_id, scope_id)
                    try:
                        merged = learning.normalize_policy({**current_learning["policy"], **learning_policy})
                    except learning.RuntimeLearningError as exc:
                        raise ExecutionRepositoryError(str(exc)) from exc
                    learning_version = current_learning["version"] + 1
                    learning_policy_digest = learning.digest(merged)
                    if merged != current_learning["policy"]:
                        changed_sections.append("tenant_learning")
                    self._write_learning_policy_locked(tenant_id, scope_id, merged, learning_version, instant)
                version = expected_version + 1
                self._write_runtime_control_policy_locked(policy, version, instant)
                receipt = self._append_runtime_control_event_locked(tenant_id=tenant_id, actor_id=actor_id,
                    version=version, policy=policy, previous_policy=current["policy"], changed_sections=changed_sections,
                    learning_policy_digest=learning_policy_digest, instant=instant)
                self._connection.execute("COMMIT")
                return {"version": version, "policy": dict(policy), "learning_policy_version": learning_version,
                        "receipt": receipt}
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def runtime_control_history(self, *, tenant_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Bounded immutable control receipts for the authenticated tenant only."""
        tenant_id, _ = self._learning_scope(tenant_id, "tenant")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ExecutionRepositoryError("runtime control history limit must be in [1, 100]")
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM ai_execution_runtime_control_event
                   WHERE namespace = ? AND tenant_id = ? ORDER BY version DESC LIMIT ?""",
                (self.namespace, tenant_id, limit),
            ).fetchall()
            history = []
            for row in rows:
                raw = row["receipt_json"]
                if not isinstance(raw, str) or len(raw) > 4096:
                    raise ExecutionRepositoryCorruption("runtime control receipt exceeds its storage bound")
                receipt = _json_object(raw, "runtime control receipt")
                expected_fields = {
                    "schema_version", "tenant_id", "version", "actor_digest", "policy_digest",
                    "previous_policy_digest", "learning_policy_digest", "changed_sections", "updated_at",
                }
                if set(receipt) not in (expected_fields, expected_fields | {"learning_checkpoint"}) or receipt.get("schema_version") != "skeleton.runtime.control.event.v1":
                    raise ExecutionRepositoryCorruption("runtime control receipt schema differs")
                if learning.digest(receipt) != row["receipt_digest"] or receipt.get("tenant_id") != tenant_id or receipt.get("version") != int(row["version"]):
                    raise ExecutionRepositoryCorruption("runtime control receipt identity differs")
                for name in ("actor_digest", "policy_digest", "previous_policy_digest", "learning_policy_digest"):
                    value = receipt[name]
                    if value != row[name] or (value is not None and (not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value))):
                        raise ExecutionRepositoryCorruption("runtime control receipt digest fields differ")
                sections = receipt["changed_sections"]
                if not isinstance(sections, list) or len(sections) > 3 or any(not isinstance(section, str) or section not in {"global_policy", "tenant_learning", "learning_checkpoint"} for section in sections) or _json_dump(sections) != row["changed_sections_json"]:
                    raise ExecutionRepositoryCorruption("runtime control receipt sections differ")
                mutation = receipt.get("learning_checkpoint")
                if mutation is not None:
                    mutation_fields = {"partition_id", "action", "model_selection_digest", "previous_state_version",
                        "state_version", "previous_state_digest", "state_digest", "checkpoint_digest"}
                    if not isinstance(mutation, dict) or set(mutation) != mutation_fields or not isinstance(mutation["action"], str) or mutation["action"] not in {"import", "reset", "restore_last_healthy"}:
                        raise ExecutionRepositoryCorruption("runtime control checkpoint receipt differs")
                    try:
                        for name in ("partition_id", "model_selection_digest", "previous_state_digest", "state_digest"):
                            learning._sha(mutation[name], name)
                        if mutation["checkpoint_digest"] is not None:
                            learning._sha(mutation["checkpoint_digest"], "checkpoint_digest")
                        learning._integer(mutation["previous_state_version"], "previous_state_version", 1, learning.MAX_COUNTER)
                        learning._integer(mutation["state_version"], "state_version", 1, learning.MAX_COUNTER)
                    except learning.RuntimeLearningError as exc:
                        raise ExecutionRepositoryCorruption("runtime control checkpoint receipt metadata differs") from exc
                if receipt["updated_at"] != row["updated_at"]:
                    raise ExecutionRepositoryCorruption("runtime control receipt timestamp differs")
                _parse_time(receipt["updated_at"], "runtime control receipt updated_at")
                history.append({**receipt, "receipt_digest": row["receipt_digest"]})
            return history

    @staticmethod
    def _empty_learning_totals() -> dict[str, Any]:
        return {
            "outcomes": 0, "completed": 0, "degraded": 0, "failed": 0, "cancelled": 0,
            "resource_failures": 0, "telemetry_errors": 0, "trained_outcomes": 0,
            "total_elapsed_seconds": 0.0, "input_tokens": 0, "output_tokens": 0,
            "provider_attempts": 0, "cost_usd": 0.0,
        }

    def _learning_totals_locked(self, tenant_id: str, scope_id: str) -> tuple[dict[str, Any], int]:
        row = self._connection.execute(
            """SELECT * FROM ai_execution_learning_totals
               WHERE namespace = ? AND tenant_id = ? AND scope_id = ?""",
            (self.namespace, tenant_id, scope_id),
        ).fetchone()
        if row is None:
            return self._empty_learning_totals(), 0
        totals = _json_object(row["totals_json"], "learning totals")
        if learning.digest(totals) != row["totals_digest"]:
            raise ExecutionRepositoryCorruption("runtime learning totals digest differs")
        expected = self._empty_learning_totals()
        if set(totals) != set(expected):
            raise ExecutionRepositoryCorruption("runtime learning totals schema differs")
        for key, value in totals.items():
            try:
                learning._finite(value, key, 0, learning.MAX_COUNTER)
            except learning.RuntimeLearningError as exc:
                raise ExecutionRepositoryCorruption("runtime learning totals are invalid") from exc
        return totals, int(row["version"])

    def _learning_state_locked(self, row: sqlite3.Row | None, *, seed: str) -> dict[str, Any] | None:
        if row is None:
            return None
        state = None
        binding_differs = False
        try:
            raw = row["state_json"]
            if not isinstance(raw, str) or len(raw) > learning.MAX_STATE_BYTES:
                raise learning.RuntimeLearningError("optimizer storage bound differs")
            state = _json_object(raw, "learning optimizer")
            provenance = state.get("provenance", {})
            if not isinstance(provenance, dict):
                binding_differs = True
                raise learning.RuntimeLearningError("optimizer activation binding differs")
            if isinstance(provenance, dict) and (
                not isinstance(provenance.get("partition_id", ""), str)
                or not isinstance(provenance.get("model_selection_digest", ""), str)
                or provenance.get("partition_id", "") not in {"", row["partition_id"]}
                or provenance.get("model_selection_digest", "") not in {"", row["model_selection_digest"]}
            ):
                binding_differs = True
                raise learning.RuntimeLearningError("optimizer activation binding differs")
            if learning.digest(state) != row["state_digest"]:
                raise learning.RuntimeLearningError("optimizer digest differs")
            learning.validate_state(state)
            learning.upgrade_state(state)
            state["provenance"].update({"partition_id": row["partition_id"], "model_selection_digest": row["model_selection_digest"]})
            return state
        except (ExecutionRepositoryCorruption, ValueError, TypeError, RecursionError, OverflowError) as exc:
            if not binding_differs:
                try:
                    recovered = learning.recover_last_healthy(state, seed=seed, policy=learning.normalize_policy(), reason=f"persisted_optimizer:{type(exc).__name__}")
                    recovered["provenance"].update({"partition_id": row["partition_id"], "model_selection_digest": row["model_selection_digest"]})
                    return recovered
                except (learning.RuntimeLearningError, ArithmeticError):
                    pass
            prior = hashlib.sha256(str(row["state_json"]).encode()).hexdigest()
            return learning.quarantine_state(seed, reason=str(exc), prior_digest=prior)

    def _save_learning_state_locked(
        self, identity: dict[str, Any], state: dict[str, Any], previous: sqlite3.Row | None,
        instant: datetime, *, maintenance: bool = False,
    ) -> int:
        learning.upgrade_state(state)
        provenance = state["provenance"]
        if provenance["partition_id"] not in {"", identity["partition_id"]} or provenance["model_selection_digest"] not in {"", identity["model_selection_digest"]}:
            raise ExecutionRepositoryConflict("optimizer activation binding differs")
        provenance.update({"partition_id": identity["partition_id"], "model_selection_digest": identity["model_selection_digest"]})
        if not provenance["latest_source_digest"] and identity.get("source_snapshot_digest"):
            provenance["latest_source_digest"] = identity["source_snapshot_digest"]
        learning.validate_state(state)
        observed_at = identity.get("observed_at") if not maintenance else None
        if observed_at is None and previous is not None:
            observed_at = previous["last_observed_at"] or previous["updated_at"]
        version = 1 if previous is None else int(previous["version"]) + 1
        state_json = _json_dump(state)
        state_digest = hashlib.sha256(state_json.encode()).hexdigest()
        self._connection.execute(
            """INSERT INTO ai_execution_learning_state(
                   namespace, tenant_id, scope_id, partition_id, task_class, model_selection_digest,
                   version, state_digest, state_json, updated_at, last_observed_at, maintenance_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(namespace, tenant_id, scope_id, partition_id) DO UPDATE SET
                   version = excluded.version, state_digest = excluded.state_digest,
                   state_json = excluded.state_json, updated_at = excluded.updated_at,
                   last_observed_at = excluded.last_observed_at,
                   maintenance_at = excluded.maintenance_at""",
            (self.namespace, identity["tenant_id"], identity["scope_id"], identity["partition_id"],
             identity["task_class"], identity["model_selection_digest"], version,
             state_digest, state_json, instant.isoformat(), observed_at,
             instant.isoformat() if maintenance else (None if previous is None else previous["maintenance_at"])),
        )
        return version

    @staticmethod
    def _learning_observation_age(
        state: dict[str, Any] | None, *, now: datetime | None = None
    ) -> float | None:
        """Read evidence age without treating replay/maintenance writes as outcomes."""
        if state is None:
            return None
        provenance = state.get("provenance")
        raw = provenance.get("last_observation_at") if isinstance(provenance, dict) else None
        if raw is None:
            return None
        try:
            instant = _utc(now)
            observed = _parse_time(raw, "learning observation time")
            if observed > instant + timedelta(minutes=5):
                return None
            return min(float(learning.MAX_COUNTER), max(0.0, (instant - observed).total_seconds()))
        except (ExecutionRepositoryError, ValueError, TypeError, ArithmeticError):
            return None

    @staticmethod
    def _learning_observation_base(observation: dict[str, Any]) -> dict[str, Any]:
        return {name: value for name, value in observation.items() if name != "retired_inactive_partition"}

    def _write_learning_marker_locked(
        self,
        execution_id: str,
        observation: dict[str, Any],
        *,
        trained: bool,
        learning_status: str,
        checkpoint_version: int,
        policy_version: int | None = None,
        policy_digest: str | None = None,
    ) -> None:
        digest = learning.digest(self._learning_observation_base(observation))
        row = self._connection.execute(
            """SELECT result_digest, learning_outcome_id, learning_observation_digest
               FROM ai_execution_result WHERE namespace = ? AND execution_id = ?""",
            (self.namespace, execution_id),
        ).fetchone()
        if row is None or row["result_digest"] != observation["result_digest"]:
            raise ExecutionRepositoryCorruption("learning marker requires its canonical terminal result")
        if row["learning_outcome_id"] is not None:
            if row["learning_outcome_id"] != observation["outcome_id"] or row["learning_observation_digest"] != digest:
                raise ExecutionRepositoryConflict("durable learning feedback marker differs")
            return
        self._connection.execute(
            """UPDATE ai_execution_result SET learning_outcome_id = ?, learning_observation_digest = ?,
                   learning_observed_at = ?, learning_trained = ?, learning_status = ?, learning_checkpoint_version = ?,
                   learning_tenant_id = ?, learning_scope_id = ?, learning_partition_id = ?,
                   learning_model_selection_digest = ?, learning_source_snapshot_digest = ?,
                   learning_policy_version = ?, learning_policy_digest = ?
               WHERE namespace = ? AND execution_id = ? AND learning_outcome_id IS NULL""",
            (
                observation["outcome_id"],
                digest,
                observation["observed_at"],
                int(trained),
                learning_status,
                checkpoint_version,
                observation["tenant_id"],
                observation["scope_id"],
                observation["partition_id"],
                observation["model_selection_digest"],
                observation["source_snapshot_digest"],
                policy_version,
                policy_digest,
                self.namespace,
                execution_id,
            ),
        )

    def _observation_from_learning_marker_locked(self, marker: sqlite3.Row) -> dict[str, Any]:
        execution = self.get(marker["execution_id"])
        result = self._result_from_row(marker)
        version = int(marker["learning_checkpoint_version"] or 0)
        checkpoint_payload = None
        if version:
            checkpoint_row = self._connection.execute(
                """SELECT * FROM ai_execution_checkpoint
                   WHERE namespace = ? AND execution_id = ? AND checkpoint_version = ?""",
                (self.namespace, marker["execution_id"], version),
            ).fetchone()
            if checkpoint_row is None:
                raise ExecutionRepositoryCorruption("learning feedback checkpoint no longer exists")
            checkpoint_payload = self._checkpoint_from_row(checkpoint_row).payload
        observation = learning.terminal_observation(execution.request, result, checkpoint_payload)
        if observation["outcome_id"] != marker["learning_outcome_id"] or learning.digest(observation) != marker["learning_observation_digest"]:
            raise ExecutionRepositoryCorruption("reconstructed learning feedback digest differs")
        for name in ("tenant_id", "scope_id", "partition_id", "model_selection_digest", "source_snapshot_digest"):
            if observation[name] != marker["learning_" + name]:
                raise ExecutionRepositoryCorruption("reconstructed learning feedback scope/provenance differs")
        return observation

    def _backfill_learning_marker_locked(self, outcome: sqlite3.Row) -> bool:
        """Bounded lazy upgrade before a derived diagnostic row is removed."""
        marker = self._connection.execute(
            "SELECT * FROM ai_execution_result WHERE namespace = ? AND execution_id = ?",
            (self.namespace, outcome["execution_id"]),
        ).fetchone()
        if marker is None:
            return False
        try:
            observation = _json_object(outcome["observation_json"], "legacy learning outcome")
            if learning.digest(observation) != outcome["observation_digest"]:
                return False
            if marker["learning_outcome_id"] is not None:
                return marker["learning_outcome_id"] == outcome["outcome_id"] and marker["learning_observation_digest"] == learning.digest(self._learning_observation_base(observation))
            execution = self.get(outcome["execution_id"])
            result = self._result_from_row(marker)
            checkpoint = self.latest_checkpoint(outcome["execution_id"])
            version = 0 if checkpoint is None else checkpoint.checkpoint_version
            if observation.get("trainable") is True:
                rebuilt = learning.terminal_observation(execution.request, result, None if checkpoint is None else checkpoint.payload)
                if rebuilt != self._learning_observation_base(observation):
                    return False
            self._write_learning_marker_locked(outcome["execution_id"], observation, trained=bool(outcome["trained"]),
                learning_status=outcome["learning_status"], checkpoint_version=version)
            return True
        except (ExecutionRepositoryError, learning.RuntimeLearningError, TypeError, ValueError):
            return False

    def _learning_retention_state_locked(
        self, tenant_id: str, scope_id: str, policy_limit: int, instant: datetime
    ) -> dict[str, Any]:
        row = self._connection.execute(
            """SELECT * FROM ai_execution_learning_retention_state
               WHERE namespace = ? AND tenant_id = ? AND scope_id = ?""",
            (self.namespace, tenant_id, scope_id),
        ).fetchone()
        rebuilt = False
        if row is not None:
            try:
                for name in ("version", "pruned_rows", "skipped_rows", "live_rows"):
                    learning._integer(row[name], name, 0, learning.MAX_COUNTER)
                learning._integer(row["policy_limit"], "retention policy limit", 128, 100000)
                learning._integer(row["overflow"], "retention overflow flag", 0, 1)
            except learning.RuntimeLearningError:
                row = None
                rebuilt = True
        if row is None or int(row["policy_limit"]) != policy_limit:
            # A legacy database may contain millions of rows. Inspect only the
            # configured bound plus one and leave excess cleanup to idle work.
            count = int(self._connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT 1 FROM ai_execution_learning_outcome
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ? LIMIT ?
                   )""", (self.namespace, tenant_id, scope_id, policy_limit + 1),
            ).fetchone()[0])
            state = {"version": 0 if row is None else int(row["version"]), "policy_limit": policy_limit,
                "live_rows": count, "overflow": count > policy_limit,
                "pruned_rows": 0 if row is None else int(row["pruned_rows"]),
                "skipped_rows": 0 if row is None else int(row["skipped_rows"]),
                "last_deferred_reason": "legacy_retention_backlog" if count > policy_limit else "retention_metadata_rebuilt" if rebuilt else None}
            self._save_learning_retention_state_locked(tenant_id, scope_id, state, instant)
            return state
        return dict(row)

    def _save_learning_retention_state_locked(
        self, tenant_id: str, scope_id: str, state: dict[str, Any], instant: datetime
    ) -> None:
        state["version"] = min(learning.MAX_COUNTER, int(state["version"]) + 1)
        self._connection.execute(
            """INSERT INTO ai_execution_learning_retention_state(
                   namespace, tenant_id, scope_id, version, policy_limit, live_rows, overflow,
                   pruned_rows, skipped_rows, last_deferred_reason, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(namespace, tenant_id, scope_id) DO UPDATE SET version = excluded.version,
                   policy_limit = excluded.policy_limit, live_rows = excluded.live_rows, overflow = excluded.overflow,
                   pruned_rows = excluded.pruned_rows, skipped_rows = excluded.skipped_rows,
                   last_deferred_reason = excluded.last_deferred_reason, updated_at = excluded.updated_at""",
            (self.namespace, tenant_id, scope_id, state["version"], state["policy_limit"], state["live_rows"],
             int(bool(state["overflow"])), state["pruned_rows"], state["skipped_rows"],
             state["last_deferred_reason"], instant.isoformat()),
        )

    def _reserve_learning_diagnostic_locked(
        self, tenant_id: str, scope_id: str, policy: dict[str, Any], instant: datetime
    ) -> bool:
        state = self._learning_retention_state_locked(tenant_id, scope_id, policy["retained_outcomes"], instant)
        retained = not bool(state["overflow"])
        if retained and int(state["live_rows"]) >= policy["retained_outcomes"]:
            oldest = self._connection.execute(
                """SELECT * FROM ai_execution_learning_outcome
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ? ORDER BY observed_at, execution_id LIMIT 1""",
                (self.namespace, tenant_id, scope_id),
            ).fetchone()
            if oldest is not None and self._backfill_learning_marker_locked(oldest):
                self._connection.execute(
                    "DELETE FROM ai_execution_learning_outcome WHERE namespace = ? AND execution_id = ?",
                    (self.namespace, oldest["execution_id"]),
                )
                state["live_rows"] = max(0, int(state["live_rows"]) - 1)
                state["pruned_rows"] = min(learning.MAX_COUNTER, int(state["pruned_rows"]) + 1)
            else:
                retained = False
                state["last_deferred_reason"] = "oldest_feedback_marker_requires_repair"
        if retained:
            state["live_rows"] += 1
            state["last_deferred_reason"] = None
        else:
            state["skipped_rows"] = min(learning.MAX_COUNTER, int(state["skipped_rows"]) + 1)
        self._save_learning_retention_state_locked(tenant_id, scope_id, state, instant)
        return retained

    def _record_runtime_outcome_locked(
        self, execution: AIExecution, result: AIExecutionResult, instant: datetime
    ) -> dict[str, Any]:
        """Called inside the terminal transaction; never trusts caller rewards."""
        marker = self._connection.execute(
            """SELECT result_digest, learning_outcome_id, learning_trained, learning_status
               FROM ai_execution_result WHERE namespace = ? AND execution_id = ?""",
            (self.namespace, execution.execution_id),
        ).fetchone()
        if marker is not None and marker["learning_outcome_id"] is not None:
            if marker["result_digest"] != learning.digest(result.as_dict()):
                raise ExecutionRepositoryConflict("durable feedback terminal result differs")
            learning._sha(marker["learning_outcome_id"], "durable learning outcome identity")
            retained = self._connection.execute(
                "SELECT 1 FROM ai_execution_learning_outcome WHERE namespace = ? AND execution_id = ?",
                (self.namespace, execution.execution_id),
            ).fetchone() is not None
            return {"execution_id": execution.execution_id, "outcome_id": marker["learning_outcome_id"],
                "recorded": True, "deduplicated": True, "trained": bool(marker["learning_trained"]),
                "learning_status": marker["learning_status"], "outcome_retained": retained}
        existing = self._connection.execute(
            """SELECT * FROM ai_execution_learning_outcome
               WHERE namespace = ? AND execution_id = ?""",
            (self.namespace, execution.execution_id),
        ).fetchone()
        if existing is not None:
            if existing["request_digest"] != execution.request.identity_digest or existing["result_digest"] != learning.digest(result.as_dict()):
                raise ExecutionRepositoryConflict("runtime learning outcome identity differs")
            self._backfill_learning_marker_locked(existing)
            return {"execution_id": execution.execution_id, "outcome_id": existing["outcome_id"],
                    "recorded": True, "deduplicated": True, "trained": bool(existing["trained"]),
                    "learning_status": existing["learning_status"]}

        checkpoint = self.latest_checkpoint(execution.execution_id)
        learning_status = "observed"
        try:
            observation = learning.terminal_observation(execution.request, result, None if checkpoint is None else checkpoint.payload)
        except (learning.RuntimeLearningError, OverflowError, ValueError, TypeError) as exc:
            # Malformed optimization metadata must not prevent durable failure
            # or cancellation. Keep a minimal exact terminal identity instead.
            request_digest = execution.request.identity_digest
            result_digest = learning.digest(result.as_dict())
            observation = {
                "schema_version": learning.SCHEMA, "tenant_id": "unscoped", "scope_id": "quarantined",
                "partition_id": learning.digest({"invalid_metadata": True}), "task_class": "unknown",
                "model_selection_digest": learning.digest({}), "source_snapshot_digest": learning.digest([]),
                "execution_id": execution.execution_id, "request_digest": request_digest,
                "result_digest": result_digest, "outcome_id": learning.digest({"execution_id": execution.execution_id,
                    "request_digest": request_digest, "result_digest": result_digest}),
                "status": result.status, "error_code": "learning_metadata_invalid",
                "features": [0.0] * 12, "metrics": {"elapsed_seconds": 0.0, "input_tokens": 0,
                    "output_tokens": 0, "provider_attempts": 0, "cost_usd": 0.0,
                    "resource_failure": 0, "telemetry_errors": 1},
                "trainable": False, "observed_at": result.completed_at.isoformat(),
                "learning_error": type(exc).__name__,
            }
            learning_status = "invalid_metadata"

        tenant_id, scope_id = observation["tenant_id"], observation["scope_id"]
        seed = f"{self.namespace}:{tenant_id}:{scope_id}:{observation['partition_id']}"
        trained = False
        learning_policy_version = None
        learning_policy_digest = None
        try:
            configuration = self._learning_policy_locked(tenant_id, scope_id)
            policy = configuration["policy"]
            learning_policy_version = configuration["version"]
            learning_policy_digest = learning.digest(policy)
        except (ExecutionRepositoryCorruption, learning.RuntimeLearningError):
            policy = learning.normalize_policy({"enabled": False})
            learning_status = "policy_quarantined"
        row = self._connection.execute(
            """SELECT * FROM ai_execution_learning_state
               WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ?""",
            (self.namespace, tenant_id, scope_id, observation["partition_id"]),
        ).fetchone()
        capacity = True
        if row is None:
            count = self._connection.execute(
                """SELECT COUNT(*) FROM ai_execution_learning_state
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ?""",
                (self.namespace, tenant_id, scope_id),
            ).fetchone()[0]
            capacity = count < policy["partition_limit"]
            if not capacity and policy["enabled"] and observation["trainable"]:
                stale = self._connection.execute(
                    """SELECT partition_id, version, last_observed_at, updated_at
                       FROM ai_execution_learning_state
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ?
                       ORDER BY last_observed_at, partition_id LIMIT 1""",
                    (self.namespace, tenant_id, scope_id),
                ).fetchone()
                if stale is not None:
                    try:
                        last_seen = _parse_time(stale["last_observed_at"] or stale["updated_at"], "learning last observed")
                        if last_seen <= instant - timedelta(days=7):
                            self._connection.execute(
                                """DELETE FROM ai_execution_learning_state
                                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ? AND version = ?""",
                                (self.namespace, tenant_id, scope_id, stale["partition_id"], stale["version"]),
                            )
                            observation["retired_inactive_partition"] = stale["partition_id"]
                            capacity = True
                    except ExecutionRepositoryCorruption:
                        pass
        if policy["enabled"] and observation["trainable"] and capacity:
            state = self._learning_state_locked(row, seed=seed)
            try:
                if state is not None and state.get("fresh_observations", 0):
                    age = self._learning_observation_age(state, now=instant)
                    if age is None or age > policy["outcome_max_age_days"] * 86400:
                        state = learning.reset_confidence(state, reason="stale_evidence", policy=policy)
                state, trained = learning.learn_outcome(state, observation, policy, seed=seed)
            except (learning.RuntimeLearningError, ArithmeticError, ValueError) as exc:
                state = learning.quarantine_state(seed, reason=f"optimizer update: {type(exc).__name__}")
            self._save_learning_state_locked(observation, state, row, instant)
            learning_status = "trained" if trained else "optimizer_quarantined" if state["quarantined"] else "optimizer_rolled_back"
        elif not capacity:
            learning_status = "partition_capacity"
        elif not policy["enabled"] and learning_status == "observed":
            learning_status = "disabled"
        elif not observation["trainable"] and learning_status == "observed":
            learning_status = "audit_only"

        self._write_learning_marker_locked(
            execution.execution_id,
            observation,
            trained=trained,
            learning_status=learning_status,
            checkpoint_version=0 if checkpoint is None else checkpoint.checkpoint_version,
            policy_version=learning_policy_version,
            policy_digest=learning_policy_digest,
        )
        try:
            outcome_retained = self._reserve_learning_diagnostic_locked(tenant_id, scope_id, policy, instant)
        except (ExecutionRepositoryError, learning.RuntimeLearningError, ValueError, TypeError, OverflowError):
            # Canonical terminal feedback is already marked. Diagnostic cache
            # corruption cannot undo that result or cause a second optimizer update.
            outcome_retained = False
        if outcome_retained:
            self._connection.execute(
                """INSERT INTO ai_execution_learning_outcome(
                       namespace, execution_id, outcome_id, tenant_id, scope_id, partition_id, task_class,
                       model_selection_digest, source_snapshot_digest, request_digest, result_digest,
                       observation_digest, observation_json, trained, learning_status, observed_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.namespace, execution.execution_id, observation["outcome_id"], tenant_id, scope_id,
                 observation["partition_id"], observation["task_class"], observation["model_selection_digest"],
                 observation["source_snapshot_digest"], observation["request_digest"], observation["result_digest"],
                 learning.digest(observation), _json_dump(observation), int(trained), learning_status,
                 observation["observed_at"]),
            )
        try:
            totals, totals_version = self._learning_totals_locked(tenant_id, scope_id)
        except (ExecutionRepositoryCorruption, learning.RuntimeLearningError):
            # An invalid optimization aggregate is not terminal execution
            # authority. Preserve its quarantined bytes and the new outcome;
            # the operator sees unavailable totals instead of invented counts.
            return {"execution_id": execution.execution_id, "outcome_id": observation["outcome_id"],
                    "recorded": True, "deduplicated": False, "trained": trained,
                    "learning_status": learning_status, "totals_health": "quarantined", "outcome_retained": outcome_retained}
        metrics = observation["metrics"]
        increments = {
            "outcomes": 1, observation["status"]: 1, "trained_outcomes": int(trained),
            "resource_failures": metrics["resource_failure"], "telemetry_errors": metrics["telemetry_errors"],
            "total_elapsed_seconds": metrics["elapsed_seconds"], "input_tokens": metrics["input_tokens"],
            "output_tokens": metrics["output_tokens"], "provider_attempts": metrics["provider_attempts"],
            "cost_usd": metrics["cost_usd"],
        }
        for key, value in increments.items():
            totals[key] = min(learning.MAX_COUNTER, totals[key] + value)
        self._connection.execute(
            """INSERT INTO ai_execution_learning_totals(
                   namespace, tenant_id, scope_id, version, totals_digest, totals_json, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(namespace, tenant_id, scope_id) DO UPDATE SET version = excluded.version,
                   totals_digest = excluded.totals_digest, totals_json = excluded.totals_json,
                   updated_at = excluded.updated_at""",
            (self.namespace, tenant_id, scope_id, totals_version + 1, learning.digest(totals), _json_dump(totals), instant.isoformat()),
        )
        return {"execution_id": execution.execution_id, "outcome_id": observation["outcome_id"],
                "recorded": True, "deduplicated": False, "trained": trained, "learning_status": learning_status,
                "outcome_retained": outcome_retained}

    def record_runtime_outcome(self, execution_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        """Idempotently learn an existing canonical terminal result, never a draft."""
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                execution = self.get(execution_id)
                result = self.result(execution_id)
                if result is None or execution.state not in {ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED}:
                    raise ExecutionRepositoryError("runtime learning requires a durable terminal execution")
                outcome = self._record_runtime_outcome_locked(execution, result, instant)
                self._connection.execute("COMMIT")
                return outcome
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _learning_partition_locked(self, tenant_id: str, scope_id: str, partition_id: str) -> sqlite3.Row:
        try:
            learning._sha(partition_id, "partition_id")
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryError(str(exc)) from exc
        row = self._connection.execute(
            """SELECT * FROM ai_execution_learning_state
               WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ?""",
            (self.namespace, tenant_id, scope_id, partition_id),
        ).fetchone()
        if row is None:
            raise ExecutionRepositoryError("runtime learning partition does not exist")
        return row

    def runtime_learning_export(
        self, *, tenant_id: str, scope_id: str = "tenant", partition_id: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Export one finite numeric controller checkpoint, never request text."""
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if expected_version is not None and (isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1):
            raise ExecutionRepositoryError("expected learning state version must be positive")
        with self._lock:
            row = self._learning_partition_locked(tenant_id, scope_id, partition_id)
            if expected_version is not None and int(row["version"]) != expected_version:
                raise ExecutionRepositoryConflict("runtime learning state version changed")
            seed = f"{self.namespace}:{tenant_id}:{scope_id}:{partition_id}"
            state = self._learning_state_locked(row, seed=seed)
            state["provenance"].update({"partition_id": partition_id, "model_selection_digest": row["model_selection_digest"]})
            try:
                return learning.checkpoint_envelope(dict(row), state, state_version=int(row["version"]))
            except learning.RuntimeLearningError as exc:
                raise ExecutionRepositoryError(str(exc)) from exc

    def _validate_learning_import_provenance_locked(
        self, state: dict[str, Any], identity: sqlite3.Row, policy: dict[str, Any]
    ) -> None:
        samples = [*state["replay"], *state["recent_replay"]]
        sample_ids = sorted({sample["outcome_id"] for sample in samples})
        outcomes: dict[str, dict[str, Any]] = {}
        if sample_ids:
            placeholders = ",".join("?" for _ in sample_ids)
            rows = self._connection.execute(
                "SELECT * FROM ai_execution_learning_outcome WHERE namespace = ? AND outcome_id IN (" + placeholders + ")",
                (self.namespace, *sample_ids),
            ).fetchall()
            for row in rows:
                if any(row[name] != identity[name] for name in ("tenant_id", "scope_id", "partition_id", "model_selection_digest")):
                    raise ExecutionRepositoryError("imported replay scope/activation differs")
                observation = _json_object(row["observation_json"], "learning import outcome")
                if learning.digest(observation) != row["observation_digest"] or observation.get("trainable") is not True or not bool(row["trained"]):
                    raise ExecutionRepositoryCorruption("imported replay canonical provenance differs")
                outcomes[row["outcome_id"]] = observation
            for missing in set(sample_ids) - set(outcomes):
                marker = self._connection.execute(
                    "SELECT * FROM ai_execution_result WHERE namespace = ? AND learning_outcome_id = ?",
                    (self.namespace, missing),
                ).fetchone()
                if marker is None or any(marker["learning_" + name] != identity[name] for name in ("tenant_id", "scope_id", "partition_id", "model_selection_digest")):
                    raise ExecutionRepositoryError("imported replay requires existing canonical feedback provenance")
                if not bool(marker["learning_trained"]):
                    raise ExecutionRepositoryError("imported replay was not accepted by its original learning policy")
                outcomes[missing] = self._observation_from_learning_marker_locked(marker)
            for sample in samples:
                observation = outcomes[sample["outcome_id"]]
                if sample["features"] != observation["features"] or sample["targets"] != learning.observation_targets(observation, policy):
                    raise ExecutionRepositoryError("imported replay telemetry differs from canonical outcome")
        provenance = state["provenance"]
        sources = {item["digest"] for item in provenance["recent_sources"]}
        if provenance["latest_source_digest"]:
            sources.add(provenance["latest_source_digest"])
        for source in sources:
            found = self._connection.execute(
                """SELECT 1 FROM ai_execution_learning_outcome
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ?
                         AND source_snapshot_digest = ? LIMIT 1""",
                (self.namespace, identity["tenant_id"], identity["scope_id"], identity["partition_id"], source),
            ).fetchone()
            if found is None:
                found = self._connection.execute(
                    """SELECT 1 FROM ai_execution_result
                       WHERE namespace = ? AND learning_tenant_id = ? AND learning_scope_id = ?
                             AND learning_partition_id = ? AND learning_source_snapshot_digest = ?
                             AND learning_outcome_id IS NOT NULL LIMIT 1""",
                    (self.namespace, identity["tenant_id"], identity["scope_id"], identity["partition_id"], source),
                ).fetchone()
                if found is None:
                    raise ExecutionRepositoryError("imported source fingerprint has no canonical provenance")

    def _mutate_learning_checkpoint(
        self, *, tenant_id: str, scope_id: str, partition_id: str, expected_version: int,
        model_selection_digest: str, action: str, checkpoint: dict[str, Any] | None,
        expected_policy_version: int | None, actor_id: str | None, now: datetime | None,
    ) -> dict[str, Any]:
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise ExecutionRepositoryError("expected learning state version must be positive")
        if expected_policy_version is not None and (isinstance(expected_policy_version, bool) or not isinstance(expected_policy_version, int) or expected_policy_version < 1):
            raise ExecutionRepositoryError("expected runtime policy version must be positive")
        try:
            learning._sha(model_selection_digest, "model_selection_digest")
            if actor_id is not None:
                actor_id = learning.identifier(actor_id, "actor_id", maximum=512)
            if action == "import":
                checkpoint = learning.validate_checkpoint_envelope(checkpoint)
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryError(str(exc)) from exc
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                controls = self.runtime_control_policy()
                if expected_policy_version is not None and controls["version"] != expected_policy_version:
                    raise ExecutionRepositoryConflict("runtime control policy version changed")
                row = self._learning_partition_locked(tenant_id, scope_id, partition_id)
                if int(row["version"]) != expected_version:
                    raise ExecutionRepositoryConflict("runtime learning state version changed")
                if row["model_selection_digest"] != model_selection_digest:
                    raise ExecutionRepositoryConflict("runtime learning activation/model differs")
                seed = f"{self.namespace}:{tenant_id}:{scope_id}:{partition_id}"
                current = self._learning_state_locked(row, seed=seed)
                policy = self._learning_policy_locked(tenant_id, scope_id)["policy"]
                imported_digest = None
                if action == "import":
                    if any(checkpoint[name] != value for name, value in (
                        ("tenant_id", tenant_id), ("scope_id", scope_id), ("partition_id", partition_id),
                        ("task_class", row["task_class"]), ("model_selection_digest", model_selection_digest),
                    )):
                        raise ExecutionRepositoryConflict("learning checkpoint tenant/partition/activation differs")
                    state = json.loads(_json_dump(checkpoint["state"]))
                    if state["quarantined"]:
                        raise ExecutionRepositoryError("quarantined checkpoints require reset or healthy restore")
                    self._validate_learning_import_provenance_locked(state, row, policy)
                    imported_digest = checkpoint["checkpoint_digest"]
                    # Imported counts and health claims cannot certify advice.
                    # Retain this repository's observed/cost/source authority.
                    for name in ("observations", "lifetime_observations", "generation", "optimizer_cost", "provenance", "last_healthy", "last_rollback"):
                        state[name] = json.loads(_json_dump(current[name]))
                    state = learning.reset_confidence(state, reason="import", policy=policy)
                elif action == "restore_last_healthy":
                    state = learning.restore_last_healthy(current, reason="operator_restore", policy=policy)
                    imported_digest = state["last_healthy"]["checkpoint_digest"]
                elif action == "reset":
                    state = learning.new_state(seed)
                    for name in ("lifetime_observations", "generation", "optimizer_cost", "provenance"):
                        state[name] = json.loads(_json_dump(current[name]))
                    state = learning.reset_confidence(state, reason="reset", policy=policy)
                else:
                    raise ExecutionRepositoryError("learning checkpoint action is invalid")
                state_version = self._save_learning_state_locked(dict(row), state, row, instant)
                version = controls["version"] + 1
                self._write_runtime_control_policy_locked(controls["policy"], version, instant)
                mutation = {"partition_id": partition_id, "action": action, "model_selection_digest": model_selection_digest,
                    "previous_state_version": expected_version, "state_version": state_version,
                    "previous_state_digest": hashlib.sha256(str(row["state_json"]).encode()).hexdigest(),
                    "state_digest": learning.digest(state),
                    "checkpoint_digest": imported_digest}
                receipt = self._append_runtime_control_event_locked(tenant_id=tenant_id, actor_id=actor_id,
                    version=version, policy=controls["policy"], previous_policy=controls["policy"],
                    changed_sections=["learning_checkpoint"], learning_policy_digest=learning.digest(policy),
                    instant=instant, learning_checkpoint=mutation)
                self._connection.execute("COMMIT")
                return {
                    "version": version,
                    "state_version": state_version,
                    "partition_id": partition_id,
                    "model_selection_digest": model_selection_digest,
                    "receipt": receipt,
                    **learning.state_readiness(
                        state, policy, observed_age_seconds=self._learning_observation_age(state, now=instant)
                    ),
                }
            except learning.RuntimeLearningError as exc:
                self._connection.execute("ROLLBACK")
                raise ExecutionRepositoryError(str(exc)) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def runtime_learning_import(
        self, *, tenant_id: str, scope_id: str = "tenant", partition_id: str,
        checkpoint: dict[str, Any], expected_version: int, model_selection_digest: str,
        expected_policy_version: int | None = None, actor_id: str | None = None, now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._mutate_learning_checkpoint(tenant_id=tenant_id, scope_id=scope_id, partition_id=partition_id,
            checkpoint=checkpoint, expected_version=expected_version, model_selection_digest=model_selection_digest,
            action="import", expected_policy_version=expected_policy_version, actor_id=actor_id, now=now)

    def runtime_learning_reset(
        self, *, tenant_id: str, scope_id: str = "tenant", partition_id: str, expected_version: int,
        model_selection_digest: str, to_last_healthy: bool = False,
        expected_policy_version: int | None = None, actor_id: str | None = None, now: datetime | None = None,
    ) -> dict[str, Any]:
        if type(to_last_healthy) is not bool:
            raise ExecutionRepositoryError("to_last_healthy must be boolean")
        return self._mutate_learning_checkpoint(tenant_id=tenant_id, scope_id=scope_id, partition_id=partition_id,
            checkpoint=None, expected_version=expected_version, model_selection_digest=model_selection_digest,
            action="restore_last_healthy" if to_last_healthy else "reset",
            expected_policy_version=expected_policy_version, actor_id=actor_id, now=now)

    def runtime_learning_snapshot(
        self, *, tenant_id: str, scope_id: str = "tenant", limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ExecutionRepositoryError("learning snapshot limit must be in [1, 100]")
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 127:
            raise ExecutionRepositoryError("learning snapshot offset must be in [0, 127]")
        instant = _utc()
        with self._lock:
            configuration = self._learning_policy_locked(tenant_id, scope_id)
            policy = configuration["policy"]
            totals_health = "healthy"
            try:
                totals, _ = self._learning_totals_locked(tenant_id, scope_id)
            except (ExecutionRepositoryCorruption, learning.RuntimeLearningError):
                totals = None
                totals_health = "quarantined"
            rows = self._connection.execute(
                """SELECT * FROM ai_execution_learning_state
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ?
                   ORDER BY updated_at DESC, partition_id LIMIT ? OFFSET ?""",
                (self.namespace, tenant_id, scope_id, limit, offset),
            ).fetchall()
            total_partitions = int(self._connection.execute(
                """SELECT COUNT(*) FROM ai_execution_learning_state
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ?""",
                (self.namespace, tenant_id, scope_id),
            ).fetchone()[0])
            partitions = []
            for row in rows:
                seed = f"{self.namespace}:{tenant_id}:{scope_id}:{row['partition_id']}"
                state = self._learning_state_locked(row, seed=seed)
                partitions.append(
                    {
                        "partition_id": row["partition_id"],
                        "task_class": row["task_class"],
                        "model_selection_digest": row["model_selection_digest"],
                        "state_version": int(row["version"]),
                        "last_observed_at": row["last_observed_at"] or row["updated_at"],
                        "last_updated_at": row["updated_at"],
                        **learning.state_readiness(
                            state,
                            policy,
                            observed_age_seconds=self._learning_observation_age(state, now=instant),
                        ),
                    }
                )
            recent_rows = self._connection.execute(
                """SELECT execution_id, model_selection_digest, source_snapshot_digest, observation_json,
                          observation_digest, trained, learning_status, observed_at
                   FROM ai_execution_learning_outcome
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ?
                   ORDER BY observed_at DESC, execution_id LIMIT ?""",
                (self.namespace, tenant_id, scope_id, limit),
            ).fetchall()
            recent = []
            recent_outcome_errors = 0
            for row in recent_rows:
                try:
                    observation = _json_object(row["observation_json"], "runtime learning outcome")
                    if learning.digest(observation) != row["observation_digest"]:
                        raise ExecutionRepositoryCorruption("runtime learning outcome digest differs")
                    if not isinstance(observation.get("metrics"), dict):
                        raise ExecutionRepositoryCorruption("runtime learning outcome metrics differ")
                except (ExecutionRepositoryCorruption, learning.RuntimeLearningError, ValueError, TypeError):
                    recent_outcome_errors += 1
                    recent.append({"execution_id": row["execution_id"], "status": "unavailable",
                        "error_code": "outcome_integrity_invalid", "elapsed_seconds": None,
                        "source_snapshot_digest": row["source_snapshot_digest"],
                        "model_selection_digest": row["model_selection_digest"], "observed_at": row["observed_at"],
                        "trained": False, "learning_status": "outcome_quarantined"})
                    continue
                recent.append({"execution_id": row["execution_id"], "status": observation["status"],
                    "error_code": observation["error_code"], "elapsed_seconds": observation["metrics"]["elapsed_seconds"],
                    "source_snapshot_digest": row["source_snapshot_digest"],
                    "model_selection_digest": row["model_selection_digest"], "observed_at": row["observed_at"],
                    "trained": bool(row["trained"]), "learning_status": row["learning_status"]})
            retention_row = self._connection.execute(
                """SELECT * FROM ai_execution_learning_retention_state
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ?""",
                (self.namespace, tenant_id, scope_id),
            ).fetchone()
            retention: dict[str, Any] = {"initialized": retention_row is not None,
                "policy_limit": policy["retained_outcomes"], "outcome_max_age_days": policy["outcome_max_age_days"],
                "maintenance_receipt_retention": policy["maintenance_receipt_retention"],
                "canonical_results_retained": True, "dedupe_markers_retained": True}
            if retention_row is not None:
                try:
                    for name in ("live_rows", "pruned_rows", "skipped_rows", "version"):
                        learning._integer(retention_row[name], name, 0, learning.MAX_COUNTER)
                    learning._integer(retention_row["overflow"], "retention overflow", 0, 1)
                    retention.update({"health": "healthy", "live_rows": int(retention_row["live_rows"]),
                        "live_rows_exact": not bool(retention_row["overflow"]), "overflow": bool(retention_row["overflow"]),
                        "pruned_rows": int(retention_row["pruned_rows"]), "skipped_rows": int(retention_row["skipped_rows"]),
                        "last_deferred_reason": retention_row["last_deferred_reason"]})
                except learning.RuntimeLearningError:
                    retention.update({"health": "quarantined", "live_rows": None, "live_rows_exact": False})
            return {"schema_version": "skeleton.runtime.learning.snapshot.v1", "tenant_id": tenant_id,
                "scope_id": scope_id, "policy": policy, "policy_version": configuration["version"],
                "totals": totals, "totals_health": totals_health,
                "observations": None if totals is None else totals["outcomes"], "partitions": partitions,
                "recent_outcomes": recent, "recent_outcome_errors": recent_outcome_errors,
                "retention": retention,
                "model": {"kind": "bounded_online_mlp", "architecture": [12, 16, 8, 3], "optimizer": "adam",
                    "controller_version": learning.CONTROLLER_VERSION,
                    "parameter_count": learning.PARAMETER_COUNT, "outputs": list(learning.OUTPUT_NAMES),
                    "latency_reference_seconds": learning.LATENCY_REFERENCE_SECONDS,
                    "labels": "canonical operational telemetry; not creative quality or verified correctness"},
                "limits": {"returned_partitions": len(partitions), "returned_outcomes": len(recent),
                    "partition_offset": offset, "total_partitions": total_partitions,
                    "has_more_partitions": offset + len(partitions) < total_partitions,
                    "max_optimizer_updates_per_outcome": 1 + policy["replay_steps"],
                    "retained_outcomes": policy["retained_outcomes"], "max_retention_rows_per_chunk": 512,
                    "partition_limit": policy["partition_limit"], "replay_capacity": policy["replay_capacity"]}}

    @staticmethod
    def _learning_dataset_cursor(binding: str, after: dict[str, str], watermark: dict[str, str]) -> str:
        payload = {
            "schema_version": "skeleton.runtime.learning.dataset.cursor.v1",
            "binding_digest": binding,
            "after": after,
            "watermark": watermark,
        }
        payload["cursor_digest"] = learning.digest(payload)
        return base64.urlsafe_b64encode(_json_dump(payload).encode()).decode("ascii").rstrip("=")

    @staticmethod
    def _parse_learning_dataset_cursor(cursor: str, binding: str) -> dict[str, Any]:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 4096 or cursor.strip() != cursor:
            raise ExecutionRepositoryError("learning dataset cursor exceeds its bound")
        try:
            raw = base64.b64decode(
                cursor.encode("ascii") + b"=" * (-len(cursor) % 4), altchars=b"-_", validate=True
            )
            if len(raw) > 3072:
                raise ValueError("cursor is too large")
            payload = _json_object(raw.decode("utf-8"), "learning dataset cursor")
            fields = {"schema_version", "binding_digest", "after", "watermark", "cursor_digest"}
            if (
                set(payload) != fields
                or payload["schema_version"] != "skeleton.runtime.learning.dataset.cursor.v1"
                or payload["binding_digest"] != binding
            ):
                raise ValueError("cursor scope/filter binding differs")
            if (
                learning.digest({key: value for key, value in payload.items() if key != "cursor_digest"})
                != payload["cursor_digest"]
            ):
                raise ValueError("cursor digest differs")
            for name in ("after", "watermark"):
                pair = payload[name]
                if not isinstance(pair, dict) or set(pair) != {"observed_at", "execution_id"}:
                    raise ValueError("cursor keyset differs")
                if not isinstance(pair["execution_id"], str) or not 1 <= len(pair["execution_id"]) <= 192:
                    raise ValueError("cursor execution identity differs")
                if _parse_time(pair["observed_at"], "dataset cursor time").isoformat() != pair["observed_at"]:
                    raise ValueError("cursor timestamp must be canonical UTC")
            if (payload["after"]["observed_at"], payload["after"]["execution_id"]) > (
                payload["watermark"]["observed_at"],
                payload["watermark"]["execution_id"],
            ):
                raise ValueError("cursor exceeds its watermark")
            return payload
        except (
            ValueError,
            TypeError,
            UnicodeError,
            binascii.Error,
            ExecutionRepositoryError,
            RecursionError,
        ) as exc:
            raise ExecutionRepositoryError(
                "learning dataset cursor is invalid or belongs to another scope/filter"
            ) from exc

    @staticmethod
    def _learning_dataset_row(row: sqlite3.Row) -> tuple[dict[str, Any] | None, str | None]:
        if row["canonical_request_digest"] is None or row["canonical_result_digest"] is None:
            return None, "canonical_execution_missing"
        if row["marker_outcome_id"] is None:
            return None, "feedback_marker_missing"
        try:
            raw = row["observation_json"]
            if not isinstance(raw, str) or len(raw.encode()) > 16 * 1024:
                return None, "retained_observation_bound_exceeded"
            observation = _json_object(raw, "dataset retained observation")
            if (
                observation.get("schema_version") != learning.SCHEMA
                or learning.digest(observation) != row["observation_digest"]
            ):
                return None, "retained_observation_digest_invalid"
            if (
                learning.digest(SQLiteExecutionRepository._learning_observation_base(observation))
                != row["marker_observation_digest"]
            ):
                return None, "feedback_marker_digest_invalid"
            if (
                observation["request_digest"] != row["canonical_request_digest"]
                or observation["result_digest"] != row["canonical_result_digest"]
            ):
                return None, "canonical_identity_digest_invalid"
            for name in (
                "tenant_id",
                "scope_id",
                "partition_id",
                "model_selection_digest",
                "source_snapshot_digest",
            ):
                if observation[name] != row[name] or observation[name] != row["marker_" + name]:
                    return None, "canonical_scope_provenance_invalid"
            for name in ("execution_id", "outcome_id", "request_digest", "result_digest", "observed_at"):
                if observation[name] != row[name]:
                    return None, "retained_identity_invalid"
            learning.identifier(observation["execution_id"], "execution_id")
            learning.identifier(observation["task_class"], "task_class", maximum=256)
            if (
                observation["task_class"] != row["task_class"]
                or learning.digest(
                    {
                        "task_class": observation["task_class"],
                        "model_selection_digest": observation["model_selection_digest"],
                    }
                )
                != observation["partition_id"]
            ):
                return None, "canonical_partition_binding_invalid"
            if (
                _parse_time(observation["observed_at"], "dataset observation time").isoformat()
                != observation["observed_at"]
            ):
                return None, "retained_timestamp_invalid"
            if observation["observed_at"] != row["marker_observed_at"]:
                return None, "canonical_timestamp_invalid"
            learning._integer(row["trained"], "retained training acceptance", 0, 1)
            learning._integer(row["marker_trained"], "canonical training acceptance", 0, 1)
            if (
                observation["outcome_id"] != row["marker_outcome_id"]
                or bool(row["trained"]) != bool(row["marker_trained"])
                or row["learning_status"] != row["marker_learning_status"]
            ):
                return None, "feedback_acceptance_invalid"
            if (
                observation["status"] not in {"completed", "degraded", "failed", "cancelled"}
                or type(observation["trainable"]) is not bool
            ):
                return None, "terminal_label_invalid"
            for name in (
                "outcome_id",
                "request_digest",
                "result_digest",
                "partition_id",
                "model_selection_digest",
                "source_snapshot_digest",
            ):
                learning._sha(observation[name], name)
            features = learning._vector(observation["features"], 12, "dataset features", 0.0, 1.0)
            metrics = observation["metrics"]
            if not isinstance(metrics, dict):
                return None, "retained_metrics_invalid"
            metric_limits = {
                "elapsed_seconds": 315576000.0,
                "input_tokens": learning.MAX_COUNTER,
                "output_tokens": learning.MAX_COUNTER,
                "provider_attempts": learning.MAX_COUNTER,
                "cost_usd": 1000000000.0,
                "model_turns": learning.MAX_COUNTER,
                "tool_calls": learning.MAX_COUNTER,
                "resource_failure": 1,
                "telemetry_errors": learning.MAX_COUNTER,
            }
            usage = {
                name: learning._finite(metrics.get(name, 0), name, 0, maximum)
                for name, maximum in metric_limits.items()
            }
            version = learning._integer(
                row["marker_checkpoint_version"], "canonical checkpoint version", 0, learning.MAX_COUNTER
            )
            checkpoint_digest = row["canonical_checkpoint_digest"]
            if version:
                learning._sha(checkpoint_digest, "canonical checkpoint digest")
            elif checkpoint_digest is not None:
                return None, "canonical_checkpoint_invalid"
            policy_version, policy_digest = row["marker_policy_version"], row["marker_policy_digest"]
            if policy_version is not None or policy_digest is not None:
                learning._integer(policy_version, "learning policy version", 1, learning.MAX_COUNTER)
                learning._sha(policy_digest, "learning policy digest")
            sample = {
                "execution_id": row["execution_id"],
                "outcome_id": observation["outcome_id"],
                "observed_at": observation["observed_at"],
                "task_class": observation["task_class"],
                "partition_id": observation["partition_id"],
                "model_selection_digest": observation["model_selection_digest"],
                "source_snapshot_digest": observation["source_snapshot_digest"],
                "request_digest": observation["request_digest"],
                "result_digest": observation["result_digest"],
                "observation_digest": row["observation_digest"],
                "feedback_digest": row["marker_observation_digest"],
                "canonical_checkpoint_version": version,
                "canonical_checkpoint_digest": checkpoint_digest,
                "learning_policy_version": policy_version,
                "learning_policy_digest": policy_digest,
                "policy_provenance": "legacy_unknown" if policy_version is None else "atomic_feedback_marker",
                "features": features,
                "targets": learning.observation_targets(observation, learning.DEFAULT_POLICY),
                "usage": usage,
                "status": observation["status"],
                "training_eligibility": observation["trainable"],
                "trained_online": bool(row["trained"]),
                "provenance_verified": True,
                "provenance_basis": "canonical_feedback_marker",
            }
            sample["sample_digest"] = learning.digest(sample)
            return sample, None
        except (
            ExecutionRepositoryError,
            learning.RuntimeLearningError,
            KeyError,
            ValueError,
            TypeError,
            OverflowError,
            RecursionError,
        ):
            return None, "retained_numeric_provenance_invalid"

    def runtime_learning_dataset_export(
        self,
        *,
        tenant_id: str,
        scope_id: str = "tenant",
        limit: int = 128,
        cursor: str | None = None,
        partition_id: str | None = None,
        include_untrained: bool = False,
    ) -> dict[str, Any]:
        """Read one bounded numeric telemetry page without exposing task content.

        A fixed chronological watermark limits continuation pages. Retention
        and late arrivals can change membership between page reads; this is not
        an immutable historical snapshot or a provider-weight training grant.
        """
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
            raise ExecutionRepositoryError("learning dataset page limit must be in [1, 256]")
        if type(include_untrained) is not bool:
            raise ExecutionRepositoryError("include_untrained must be boolean")
        if partition_id is not None:
            try:
                learning._sha(partition_id, "partition_id")
            except learning.RuntimeLearningError as exc:
                raise ExecutionRepositoryError(str(exc)) from exc
        filters = {"partition_id": partition_id, "include_untrained": include_untrained}
        binding = learning.digest(
            {
                "tenant_id": tenant_id,
                "scope_id": scope_id,
                "filters": filters,
                "feature_schema": learning.FEATURE_SCHEMA,
            }
        )
        decoded = None if cursor is None else self._parse_learning_dataset_cursor(cursor, binding)
        after = None if decoded is None else decoded["after"]
        watermark = None if decoded is None else decoded["watermark"]
        parameters: list[Any] = [self.namespace, tenant_id, scope_id]
        where = "o.namespace = ? AND o.tenant_id = ? AND o.scope_id = ?"
        if partition_id is not None:
            where += " AND o.partition_id = ?"
            parameters.append(partition_id)
        if not include_untrained:
            where += " AND o.trained = 1"
        with self._lock:
            if self._connection.in_transaction:
                raise ExecutionRepositoryError("dataset export requires an independent read transaction")
            self._connection.execute("BEGIN")
            try:
                if watermark is None:
                    last = self._connection.execute(
                        "SELECT o.observed_at, o.execution_id FROM ai_execution_learning_outcome o WHERE "
                        + where
                        + " ORDER BY o.observed_at DESC, o.execution_id DESC LIMIT 1",
                        parameters,
                    ).fetchone()
                    watermark = (
                        None
                        if last is None
                        else {"observed_at": last["observed_at"], "execution_id": last["execution_id"]}
                    )
                candidates = []
                if watermark is not None:
                    page_where = where + " AND (o.observed_at, o.execution_id) <= (?, ?)"
                    page_parameters = [*parameters, watermark["observed_at"], watermark["execution_id"]]
                    if after is not None:
                        page_where += " AND (o.observed_at, o.execution_id) > (?, ?)"
                        page_parameters.extend((after["observed_at"], after["execution_id"]))
                    candidates = self._connection.execute(
                        """SELECT o.execution_id, o.outcome_id, o.tenant_id, o.scope_id, o.partition_id, o.task_class,
                           o.model_selection_digest, o.source_snapshot_digest, o.request_digest, o.result_digest,
                           o.observation_digest, o.trained, o.learning_status, o.observed_at,
                           CASE WHEN length(CAST(o.observation_json AS BLOB)) <= 16384
                                THEN o.observation_json ELSE NULL END AS observation_json,
                           s.identity_digest AS canonical_request_digest, r.result_digest AS canonical_result_digest,
                           r.learning_outcome_id AS marker_outcome_id, r.learning_observation_digest AS marker_observation_digest,
                           r.learning_tenant_id AS marker_tenant_id, r.learning_scope_id AS marker_scope_id,
                           r.learning_partition_id AS marker_partition_id, r.learning_model_selection_digest AS marker_model_selection_digest,
                           r.learning_source_snapshot_digest AS marker_source_snapshot_digest,
                           r.learning_checkpoint_version AS marker_checkpoint_version, r.learning_trained AS marker_trained,
                           r.learning_observed_at AS marker_observed_at,
                           r.learning_status AS marker_learning_status, r.learning_policy_version AS marker_policy_version,
                           r.learning_policy_digest AS marker_policy_digest, c.checkpoint_digest AS canonical_checkpoint_digest
                           FROM ai_execution_learning_outcome o
                           LEFT JOIN ai_execution_state s ON s.namespace = o.namespace AND s.execution_id = o.execution_id
                           LEFT JOIN ai_execution_result r ON r.namespace = o.namespace AND r.execution_id = o.execution_id
                           LEFT JOIN ai_execution_checkpoint c ON c.namespace = o.namespace AND c.execution_id = o.execution_id
                                AND c.checkpoint_version = r.learning_checkpoint_version
                           WHERE """
                        + page_where
                        + " ORDER BY o.observed_at, o.execution_id LIMIT ?",
                        (*page_parameters, limit + 1),
                    ).fetchall()
                rows, omitted = [], []
                last_scanned = after
                encoded_rows = 0
                scanned = 0
                for candidate in candidates[:limit]:
                    sample, reason = self._learning_dataset_row(candidate)
                    entry = (
                        sample
                        if sample is not None
                        else {
                            "execution_id": candidate["execution_id"],
                            "outcome_id": candidate["outcome_id"],
                            "reason": reason,
                        }
                    )
                    entry_size = len(_json_dump(entry).encode())
                    if scanned and encoded_rows + entry_size > 1024 * 1024 - 64 * 1024:
                        break
                    (rows if sample is not None else omitted).append(entry)
                    encoded_rows += entry_size
                    scanned += 1
                    last_scanned = {
                        "observed_at": candidate["observed_at"],
                        "execution_id": candidate["execution_id"],
                    }
                has_more = len(candidates) > scanned
                next_cursor = None
                if has_more and last_scanned is not None and watermark is not None:
                    next_cursor = self._learning_dataset_cursor(binding, last_scanned, watermark)
                try:
                    policy = self._learning_policy_locked(tenant_id, scope_id)["policy"]
                    retention = {
                        "retained_outcomes": policy["retained_outcomes"],
                        "outcome_max_age_days": policy["outcome_max_age_days"],
                        "policy_state": "known",
                    }
                except (ExecutionRepositoryCorruption, learning.RuntimeLearningError):
                    retention = {
                        "retained_outcomes": None,
                        "outcome_max_age_days": None,
                        "policy_state": "quarantined",
                    }
                page = {
                    "schema_version": "skeleton.runtime.learning.dataset.v1",
                    "tenant_id": tenant_id,
                    "scope_id": scope_id,
                    "feature_schema": learning.FEATURE_SCHEMA,
                    "feature_names": list(learning.FEATURE_NAMES),
                    "feature_normalizers": list(learning.FEATURE_NORMALIZERS),
                    "target_names": list(learning.OUTPUT_NAMES),
                    "target_semantics": {
                        "operational_completion": {
                            "completed": 1.0,
                            "degraded": 0.35,
                            "failed": 0.0,
                            "cancelled": 0.0,
                        },
                        "resource_failure": "canonical terminal resource-failure flag",
                        "normalized_latency": {
                            "formula": "elapsed_seconds/(elapsed_seconds+reference_seconds)",
                            "reference_seconds": learning.LATENCY_REFERENCE_SECONDS,
                        },
                    },
                    "filters": filters,
                    "rows": rows,
                    "row_count": len(rows),
                    "scanned_rows": scanned,
                    "omitted_rows": omitted,
                    "next_cursor": next_cursor,
                    "has_more": has_more,
                    "watermark": watermark,
                    "window": {
                        "after": after,
                        "last_scanned": last_scanned,
                        "order": "observed_at,execution_id",
                    },
                    "retention": retention,
                    "limits": {"max_rows": 256, "max_json_bytes": 1024 * 1024, "max_cursor_bytes": 4096},
                    "limitations": [
                        "Only retained numeric diagnostics are exported; canonical historical results are not reconstructed.",
                        "Retention and late arrivals can change membership between pages; this is not an immutable historical snapshot.",
                        "Targets describe operational completion, resource failures and latency; they do not certify creative quality or factual correctness.",
                        "Export does not train, select, activate or promote provider weights, or grant tools or resources.",
                    ],
                }
                page["dataset_digest"] = learning.digest(page)
                if len(_json_dump(page).encode()) > 1024 * 1024:
                    raise ExecutionRepositoryError("learning dataset page exceeds its JSON byte bound")
                self._connection.execute("COMMIT")
                return page
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def runtime_learning_recommendation(
        self,
        *,
        tenant_id: str,
        scope_id: str = "tenant",
        request: AIExecutionRequest | None = None,
        checkpoint_payload: dict[str, Any] | None = None,
        task_class: str = "assistant.chat",
        model_binding_digest: str = "",
        source_snapshot_digest: str = "",
        pressure: float = 0.0,
        allowed_rounds: int = 1,
        requested_rounds: int = 1,
        resource_budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        try:
            if request is not None:
                identity = learning.runtime_learning_identity(request, checkpoint_payload)
                if identity["tenant_id"] != tenant_id or identity["scope_id"] != scope_id:
                    raise ExecutionRepositoryError("runtime learning request scope differs")
            else:
                task_class = learning.identifier(task_class, "task_class", maximum=256)
                if model_binding_digest and (len(model_binding_digest) != 64 or any(char not in "0123456789abcdef" for char in model_binding_digest)):
                    raise ExecutionRepositoryError("model selection digest is invalid")
                if source_snapshot_digest and (len(source_snapshot_digest) != 64 or any(char not in "0123456789abcdef" for char in source_snapshot_digest)):
                    raise ExecutionRepositoryError("source snapshot digest is invalid")
                identity = {"tenant_id": tenant_id, "scope_id": scope_id, "task_class": task_class,
                    "model_selection_digest": model_binding_digest, "source_snapshot_digest": source_snapshot_digest,
                    "partition_id": learning.digest({"task_class": task_class, "model_selection_digest": model_binding_digest})}
            features = learning.request_features(request, pressure=pressure, resource_budget=resource_budget, requested_rounds=requested_rounds)
            with self._lock:
                configuration = self._learning_policy_locked(tenant_id, scope_id)
                row = self._connection.execute(
                    """SELECT * FROM ai_execution_learning_state
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ?""",
                    (self.namespace, tenant_id, scope_id, identity["partition_id"]),
                ).fetchone()
                seed = f"{self.namespace}:{tenant_id}:{scope_id}:{identity['partition_id']}"
                state = self._learning_state_locked(row, seed=seed)
                result = learning.recommend(
                    state,
                    configuration["policy"],
                    features,
                    allowed_rounds=allowed_rounds,
                    requested_rounds=requested_rounds,
                    pressure=pressure,
                    source_snapshot_digest=identity["source_snapshot_digest"] or None,
                    observed_age_seconds=self._learning_observation_age(state),
                )
                return {**result, **identity, "policy_version": configuration["version"],
                    "state_version": 0 if row is None else int(row["version"])}
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryError(str(exc)) from exc

    def runtime_learning_retention(
        self, *, tenant_id: str, scope_id: str = "tenant", max_rows: int = 128, now: datetime | None = None
    ) -> dict[str, Any]:
        """Bound derived diagnostics and compact only verified consumed receipts.

        Canonical terminal payloads, feedback dedupe markers, cumulative
        operational totals, optimizer state and operator audit are retained.
        """
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= 512:
            raise ExecutionRepositoryError("learning retention row bound must be in [1, 512]")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                policy = self._learning_policy_locked(tenant_id, scope_id)["policy"]
                state = self._learning_retention_state_locked(tenant_id, scope_id, policy["retained_outcomes"], instant)
                outcome_budget = max(1, max_rows // 2)
                cutoff = (instant - timedelta(days=policy["outcome_max_age_days"])).isoformat()
                candidates = self._connection.execute(
                    """SELECT * FROM ai_execution_learning_outcome
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND observed_at < ?
                       ORDER BY observed_at, execution_id LIMIT ?""",
                    (self.namespace, tenant_id, scope_id, cutoff, outcome_budget),
                ).fetchall()
                selected = {row["execution_id"]: row for row in candidates}
                if len(selected) < outcome_budget:
                    excess = self._connection.execute(
                        """SELECT * FROM ai_execution_learning_outcome
                           WHERE namespace = ? AND tenant_id = ? AND scope_id = ?
                           ORDER BY observed_at DESC, execution_id DESC LIMIT ? OFFSET ?""",
                        (self.namespace, tenant_id, scope_id, outcome_budget - len(selected), policy["retained_outcomes"]),
                    ).fetchall()
                    for row in excess:
                        selected.setdefault(row["execution_id"], row)
                pruned = failures = 0
                for row in selected.values():
                    if not self._backfill_learning_marker_locked(row):
                        failures += 1
                        continue
                    cursor = self._connection.execute(
                        "DELETE FROM ai_execution_learning_outcome WHERE namespace = ? AND execution_id = ?",
                        (self.namespace, row["execution_id"]),
                    )
                    pruned += cursor.rowcount
                count = int(self._connection.execute(
                    """SELECT COUNT(*) FROM (
                           SELECT 1 FROM ai_execution_learning_outcome
                           WHERE namespace = ? AND tenant_id = ? AND scope_id = ? LIMIT ?
                       )""", (self.namespace, tenant_id, scope_id, policy["retained_outcomes"] + 1),
                ).fetchone()[0])
                state.update({"live_rows": count, "overflow": count > policy["retained_outcomes"],
                    "pruned_rows": min(learning.MAX_COUNTER, int(state["pruned_rows"]) + pruned),
                    "last_deferred_reason": "feedback_marker_requires_repair" if failures else "legacy_retention_backlog" if count > policy["retained_outcomes"] else None})
                self._save_learning_retention_state_locked(tenant_id, scope_id, state, instant)
                receipt_budget = max_rows - len(selected)
                compacted = 0
                if receipt_budget:
                    receipts = self._connection.execute(
                        """SELECT idempotency_key FROM ai_execution_learning_maintenance_receipt
                           WHERE namespace = ? AND tenant_id = ? AND scope_id = ?
                                 AND acknowledged_at IS NOT NULL AND compacted_at IS NULL
                           ORDER BY acknowledged_at DESC, idempotency_key DESC LIMIT ? OFFSET ?""",
                        (self.namespace, tenant_id, scope_id, receipt_budget, policy["maintenance_receipt_retention"]),
                    ).fetchall()
                    for receipt in receipts:
                        cursor = self._connection.execute(
                            """UPDATE ai_execution_learning_maintenance_receipt
                               SET result_json = '', compacted_at = ?
                               WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND idempotency_key = ?
                                     AND acknowledged_at IS NOT NULL AND compacted_at IS NULL""",
                            (instant.isoformat(), self.namespace, tenant_id, scope_id, receipt["idempotency_key"]),
                        )
                        compacted += cursor.rowcount
                self._connection.execute("COMMIT")
                return {"schema_version": "skeleton.runtime.learning.retention.v1", "tenant_id": tenant_id,
                    "scope_id": scope_id, "pruned_outcomes": pruned, "compacted_maintenance_receipts": compacted,
                    "marker_backfill_failures": failures, "retained_outcomes": count,
                    "retained_outcomes_exact": not bool(state["overflow"]), "overflow": bool(state["overflow"]),
                    "terminal_results_removed": 0, "idempotency_tombstones_removed": 0,
                    "cumulative_totals_unchanged": True, "completed_at": instant.isoformat()}
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _learning_recovery_observations_locked(
        self, tenant_id: str, scope_id: str, partition_id: str
    ) -> list[dict[str, Any]]:
        observations: dict[str, dict[str, Any]] = {}
        markers = self._connection.execute(
            """SELECT * FROM ai_execution_result
               WHERE namespace = ? AND learning_tenant_id = ? AND learning_scope_id = ?
                     AND learning_partition_id = ? AND learning_outcome_id IS NOT NULL AND learning_trained = 1
               ORDER BY learning_observed_at DESC LIMIT 4""",
            (self.namespace, tenant_id, scope_id, partition_id),
        ).fetchall()
        for marker in markers:
            observation = self._observation_from_learning_marker_locked(marker)
            observations[observation["outcome_id"]] = observation
        if len(observations) < 4:
            legacy = self._connection.execute(
                """SELECT * FROM ai_execution_learning_outcome
                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ? AND trained = 1
                   ORDER BY observed_at DESC LIMIT 4""",
                (self.namespace, tenant_id, scope_id, partition_id),
            ).fetchall()
            for row in legacy:
                if row["outcome_id"] in observations or not self._backfill_learning_marker_locked(row):
                    continue
                marker = self._connection.execute(
                    "SELECT * FROM ai_execution_result WHERE namespace = ? AND execution_id = ?",
                    (self.namespace, row["execution_id"]),
                ).fetchone()
                observation = self._observation_from_learning_marker_locked(marker)
                observations[observation["outcome_id"]] = observation
        newest = sorted(observations.values(), key=lambda item: (item["observed_at"], item["execution_id"]), reverse=True)[:4]
        return list(reversed(newest))

    def _learning_maintenance_result_locked(
        self, result: dict[str, Any], *, tenant_id: str, scope_id: str,
        idempotency_key: str | None, binding_digest: str | None, instant: datetime,
    ) -> dict[str, Any]:
        if idempotency_key is None:
            return result
        payload = {**result, "idempotency_key": idempotency_key, "binding_digest": binding_digest}
        result_digest = learning.digest(payload)
        if len(_json_dump(payload).encode()) > 128 * 1024:
            raise ExecutionRepositoryError("learning maintenance receipt exceeds its storage bound")
        self._connection.execute(
            """INSERT INTO ai_execution_learning_maintenance_receipt(
                   namespace, tenant_id, scope_id, idempotency_key, binding_digest,
                   result_digest, result_json, completed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.namespace, tenant_id, scope_id, idempotency_key, binding_digest,
             result_digest, _json_dump(payload), instant.isoformat()),
        )
        return {**payload, "maintenance_receipt_digest": result_digest}

    def acknowledge_runtime_learning_maintenance(
        self, *, tenant_id: str, scope_id: str = "tenant", idempotency_key: str,
        maintenance_receipt_digest: str, completion_receipt_digest: str, now: datetime | None = None,
    ) -> dict[str, Any]:
        """Acknowledge only after the host verified and committed its chunk cursor.

        The host supplies its verified completion receipt digest. This method
        never infers success from a pending callback or from an optimizer result.
        """
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        try:
            idempotency_key = learning.identifier(idempotency_key, "idempotency_key", maximum=256)
            learning._sha(maintenance_receipt_digest, "maintenance_receipt_digest")
            learning._sha(completion_receipt_digest, "completion_receipt_digest")
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryError(str(exc)) from exc
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """SELECT * FROM ai_execution_learning_maintenance_receipt
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND idempotency_key = ?""",
                    (self.namespace, tenant_id, scope_id, idempotency_key),
                ).fetchone()
                if row is None or row["result_digest"] != maintenance_receipt_digest:
                    raise ExecutionRepositoryConflict("maintenance acknowledgement receipt identity differs")
                existing = row["acknowledgement_digest"]
                if existing is not None and existing != completion_receipt_digest:
                    raise ExecutionRepositoryConflict("maintenance completion acknowledgement already differs")
                self._connection.execute(
                    """UPDATE ai_execution_learning_maintenance_receipt
                       SET acknowledged_at = ?, acknowledgement_digest = ?
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND idempotency_key = ?
                             AND acknowledged_at IS NULL""",
                    (instant.isoformat(), completion_receipt_digest, self.namespace, tenant_id, scope_id, idempotency_key),
                )
                self._connection.execute("COMMIT")
                return {"acknowledged": True, "already_acknowledged": existing is not None,
                    "idempotency_key": idempotency_key, "maintenance_receipt_digest": maintenance_receipt_digest,
                    "completion_receipt_digest": completion_receipt_digest}
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def runtime_learning_maintenance(
        self, *, tenant_id: str, scope_id: str = "tenant", max_partitions: int = 4,
        idempotency_key: str | None = None, now: datetime | None = None
    ) -> dict[str, Any]:
        """Bounded idle replay/integrity work on this repository's existing state.

        Quarantined optimizer weights are discarded. Recovery uses at most four
        digest-checked canonical outcomes and returns to cold-start confidence.
        No provider model is trained, activated, selected, or promoted here.
        """
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(max_partitions, bool) or not isinstance(max_partitions, int) or not 1 <= max_partitions <= 8:
            raise ExecutionRepositoryError("maintenance partition bound must be in [1, 8]")
        if idempotency_key is not None:
            try:
                idempotency_key = learning.identifier(idempotency_key, "idempotency_key", maximum=256)
            except learning.RuntimeLearningError as exc:
                raise ExecutionRepositoryError(str(exc)) from exc
        binding_digest = None if idempotency_key is None else learning.digest({
            "namespace": self.namespace, "tenant_id": tenant_id, "scope_id": scope_id,
            "max_partitions": max_partitions, "idempotency_key": idempotency_key,
        })
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key is not None:
                    prior = self._connection.execute(
                        """SELECT * FROM ai_execution_learning_maintenance_receipt
                           WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND idempotency_key = ?""",
                        (self.namespace, tenant_id, scope_id, idempotency_key),
                    ).fetchone()
                    if prior is not None:
                        if prior["binding_digest"] != binding_digest:
                            raise ExecutionRepositoryConflict("learning maintenance idempotency binding differs")
                        if prior["compacted_at"] is not None:
                            if prior["acknowledged_at"] is None or prior["acknowledgement_digest"] is None:
                                raise ExecutionRepositoryCorruption("compacted maintenance receipt lacks verified acknowledgement")
                            self._connection.execute("COMMIT")
                            return {"schema_version": "skeleton.runtime.learning.maintenance.tombstone.v1",
                                "tenant_id": tenant_id, "scope_id": scope_id, "idempotency_key": idempotency_key,
                                "binding_digest": binding_digest, "maintenance_receipt_digest": prior["result_digest"],
                                "completion_receipt_digest": prior["acknowledgement_digest"],
                                "already_acknowledged": True, "compacted": True, "processed_partitions": 0,
                                "external_model_work": False, "completed_at": prior["completed_at"]}
                        if not isinstance(prior["result_json"], str) or len(prior["result_json"]) > 128 * 1024:
                            raise ExecutionRepositoryCorruption("learning maintenance receipt exceeds its storage bound")
                        previous_result = _json_object(prior["result_json"], "learning maintenance receipt")
                        if learning.digest(previous_result) != prior["result_digest"]:
                            raise ExecutionRepositoryCorruption("learning maintenance receipt digest differs")
                        self._connection.execute("COMMIT")
                        return {**previous_result, "maintenance_receipt_digest": prior["result_digest"]}
                policy = self._learning_policy_locked(tenant_id, scope_id)["policy"]
                if not policy["enabled"]:
                    result = self._learning_maintenance_result_locked({
                        "schema_version": "skeleton.runtime.learning.maintenance.v1", "tenant_id": tenant_id,
                        "scope_id": scope_id, "processed_partitions": 0, "partitions": [],
                        "deferred_reason": "learning_disabled", "external_model_work": False,
                        "completed_at": instant.isoformat()}, tenant_id=tenant_id, scope_id=scope_id,
                        idempotency_key=idempotency_key, binding_digest=binding_digest, instant=instant)
                    self._connection.execute("COMMIT")
                    return result
                rows = self._connection.execute(
                    """SELECT * FROM ai_execution_learning_state
                       WHERE namespace = ? AND tenant_id = ? AND scope_id = ?
                       ORDER BY COALESCE(maintenance_at, ''), updated_at, partition_id LIMIT ?""",
                    (self.namespace, tenant_id, scope_id, max_partitions),
                ).fetchall()
                entries = []
                for row in rows:
                    seed = f"{self.namespace}:{tenant_id}:{scope_id}:{row['partition_id']}"
                    state = self._learning_state_locked(row, seed=seed)
                    recovering = state["quarantined"]
                    updates_before = int(state["optimizer"]["step"])
                    maintenance_error = None
                    deferred_reason = None
                    try:
                        if recovering:
                            old_quarantine = state["quarantine"]
                            candidate = learning.new_state(seed)
                            recent = self._learning_recovery_observations_locked(tenant_id, scope_id, row["partition_id"])
                            for observation in recent:
                                candidate, _ = learning.learn_outcome(candidate, observation, {**policy, "replay_steps": 0}, seed=seed)
                            candidate["recovery"] = {"prior_quarantine": old_quarantine, "recovered_at": instant.isoformat()}
                            costs = candidate["optimizer_cost"]
                            costs["maintenance_updates"] = min(learning.MAX_COUNTER, costs["maintenance_updates"] + costs["terminal_updates"])
                            costs["terminal_updates"] = 0
                            # Reconstructing historical examples is replay;
                            # it cannot certify fresh prequential performance.
                            candidate = learning.reset_confidence(candidate, reason="maintenance_recovery", policy=policy)
                            state = candidate
                        elif (
                            age := self._learning_observation_age(state, now=instant)
                        ) is None or age > policy["outcome_max_age_days"] * 86400:
                            deferred_reason = "observation_time_unknown" if age is None else "outcomes_stale"
                        else:
                            state = learning.replay_maintenance(state, policy, max_updates=2)
                    except (ExecutionRepositoryError, ValueError, TypeError, ArithmeticError, RecursionError) as exc:
                        maintenance_error = type(exc).__name__
                        state = learning.quarantine_state(seed, reason=f"maintenance: {type(exc).__name__}")
                    self._save_learning_state_locked(dict(row), state, row, instant, maintenance=True)
                    entries.append(
                        {
                            "partition_id": row["partition_id"],
                            "recovered": recovering and not state["quarantined"],
                            "optimizer_updates": max(
                                0, int(state["optimizer"]["step"]) - (0 if recovering else updates_before)
                            ),
                            "maintenance_error": maintenance_error,
                            "deferred_reason": deferred_reason,
                            **learning.state_readiness(
                                state,
                                policy,
                                observed_age_seconds=self._learning_observation_age(state, now=instant),
                            ),
                        }
                    )
                result = self._learning_maintenance_result_locked({
                    "schema_version": "skeleton.runtime.learning.maintenance.v1", "tenant_id": tenant_id,
                    "scope_id": scope_id, "processed_partitions": len(entries), "partitions": entries,
                    "quarantined_partitions": sum(entry["quarantined"] for entry in entries),
                    "external_model_work": False, "completed_at": instant.isoformat()},
                    tenant_id=tenant_id, scope_id=scope_id, idempotency_key=idempotency_key,
                    binding_digest=binding_digest, instant=instant)
                self._connection.execute("COMMIT")
                return result
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def runtime_storage_maintenance(self) -> dict[str, Any]:
        """Attempt a passive WAL checkpoint without waiting on foreground work.

        This is bounded storage housekeeping, not an integrity scan, terminal
        ledger retention policy, journal-mode change, or database compaction.
        Busy readers/writers keep their pages; a later idle task can retry.
        """
        result: dict[str, Any] = {
            "mode": "passive_wal_checkpoint",
            "wal_enabled": bool(getattr(self, "_storage_wal_enabled", False)),
            "journal_mode_known": hasattr(self, "_storage_wal_enabled"),
            "busy": 0, "log_pages": 0, "checkpointed_pages": 0,
            "page_count": 0, "freelist_pages": 0, "metrics_available": False,
            "noop": True,
        }
        if not self._lock.acquire(blocking=False):
            return {**result, "busy": 1, "deferred_reason": "foreground_repository_busy"}
        previous_busy_timeout: int | None = None
        try:
            if self._connection.in_transaction:
                return {**result, "busy": 1, "deferred_reason": "foreground_transaction_active"}
            timeout_row = self._connection.execute("PRAGMA busy_timeout").fetchone()
            previous_busy_timeout = max(0, min(2147483647, int(timeout_row[0])))
            self._connection.execute("PRAGMA busy_timeout = 0")
            mode_row = self._connection.execute("PRAGMA journal_mode").fetchone()
            wal_enabled = str(mode_row[0]).lower() == "wal"
            self._storage_wal_enabled = wal_enabled
            result.update({"wal_enabled": wal_enabled, "journal_mode_known": True})
            if wal_enabled:
                checkpoint = self._connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                if checkpoint is not None:
                    for name, value in zip(("busy", "log_pages", "checkpointed_pages"), checkpoint, strict=True):
                        result[name] = max(0, min(learning.MAX_COUNTER, int(value)))
                    result["noop"] = False
            else:
                result["noop_reason"] = "journal_mode_is_not_wal"
            result["page_count"] = max(0, min(learning.MAX_COUNTER, int(self._connection.execute("PRAGMA page_count").fetchone()[0])))
            result["freelist_pages"] = max(0, min(learning.MAX_COUNTER, int(self._connection.execute("PRAGMA freelist_count").fetchone()[0])))
            result["metrics_available"] = True
            return result
        except sqlite3.OperationalError as exc:
            # PASSIVE checkpoints may encounter another checkpoint or a schema
            # writer. Do not turn that ordinary idle contention into an error.
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                return {**result, "busy": 1, "deferred_reason": "sqlite_storage_busy"}
            raise
        finally:
            try:
                if previous_busy_timeout is not None:
                    self._connection.execute(f"PRAGMA busy_timeout = {previous_busy_timeout:d}")
            finally:
                self._lock.release()

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

    def recoverable_page(
        self, *, limit: int = 32, after_updated_at: datetime | None = None,
        after_execution_id: str | None = None, include_waiting: bool = True,
    ) -> tuple[AIExecution, ...]:
        """Keyset page of unfinished executions; never loads the entire backlog.

        ``include_waiting=False`` excludes passive user/authority waiters.
        A waiter with cancellation requested remains actionable and is included
        so recovery can durably finish its cancellation after a worker crash.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 128:
            raise ExecutionRepositoryError("recoverable page limit must be in [1, 128]")
        if type(include_waiting) is not bool:
            raise ExecutionRepositoryError("include_waiting must be boolean")
        if (after_updated_at is None) != (after_execution_id is None):
            raise ExecutionRepositoryError("recovery cursor requires timestamp and execution identity together")
        condition = "state NOT IN ('completed', 'failed', 'cancelled')" if include_waiting else (
            "state NOT IN ('completed', 'failed', 'cancelled') "
            "AND (state NOT IN ('waiting_for_user', 'waiting_for_tool_authority') OR cancellation_requested = 1)"
        )
        parameters: list[Any] = [self.namespace]
        if after_updated_at is not None:
            if not isinstance(after_execution_id, str) or not 1 <= len(after_execution_id) <= 192:
                raise ExecutionRepositoryError("recovery execution cursor is invalid")
            condition += " AND (updated_at, execution_id) > (?, ?)"
            parameters.extend((_utc(after_updated_at).isoformat(), after_execution_id))
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM ai_execution_state WHERE namespace = ? AND " + condition
                + " ORDER BY updated_at, execution_id LIMIT ?", parameters,
            ).fetchall()
            return tuple(self._execution_from_row(row) for row in rows)

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
