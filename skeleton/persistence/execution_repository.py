"""Durable cognitive-execution repository and finalization outbox.

The execution repository is authoritative for execution state, turn lineage,
checkpoints, terminal results, and retry-stable finalization events. SQLite is
the deterministic reference implementation; higher-scale stores must preserve
the same compare-and-set and transactional semantics.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from skeleton.compat.datetime_utc import UTC
from datetime import datetime
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
from skeleton.intelligence import runtime_learning as learning


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
                """)
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
                self._connection.execute(
                    """INSERT INTO ai_execution_runtime_control_policy(
                           namespace, version, policy_digest, policy_json, updated_at
                       ) VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(namespace) DO UPDATE SET version = excluded.version,
                           policy_digest = excluded.policy_digest, policy_json = excluded.policy_json,
                           updated_at = excluded.updated_at""",
                    (self.namespace, version, learning.digest(policy), _json_dump(policy), instant.isoformat()),
                )
                receipt = {
                    "schema_version": "skeleton.runtime.control.event.v1",
                    "tenant_id": tenant_id, "version": version,
                    "actor_digest": None if actor_id is None else learning.digest({
                        "namespace": self.namespace, "tenant_id": tenant_id, "actor_id": actor_id,
                    }),
                    "policy_digest": learning.digest(policy),
                    "previous_policy_digest": learning.digest(current["policy"]),
                    "learning_policy_digest": learning_policy_digest,
                    "changed_sections": changed_sections,
                    "updated_at": instant.isoformat(),
                }
                receipt_digest = learning.digest(receipt)
                self._connection.execute(
                    """INSERT INTO ai_execution_runtime_control_event(
                           namespace, version, tenant_id, actor_digest, policy_digest, previous_policy_digest,
                           learning_policy_digest, changed_sections_json, receipt_digest, receipt_json, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.namespace, version, tenant_id, receipt["actor_digest"], receipt["policy_digest"],
                     receipt["previous_policy_digest"], learning_policy_digest, _json_dump(changed_sections),
                     receipt_digest, _json_dump(receipt), instant.isoformat()),
                )
                self._connection.execute("COMMIT")
                return {"version": version, "policy": dict(policy), "learning_policy_version": learning_version,
                        "receipt": {**receipt, "receipt_digest": receipt_digest}}
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
                if set(receipt) != expected_fields or receipt.get("schema_version") != "skeleton.runtime.control.event.v1":
                    raise ExecutionRepositoryCorruption("runtime control receipt schema differs")
                if learning.digest(receipt) != row["receipt_digest"] or receipt.get("tenant_id") != tenant_id or receipt.get("version") != int(row["version"]):
                    raise ExecutionRepositoryCorruption("runtime control receipt identity differs")
                for name in ("actor_digest", "policy_digest", "previous_policy_digest", "learning_policy_digest"):
                    value = receipt[name]
                    if value != row[name] or (value is not None and (not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value))):
                        raise ExecutionRepositoryCorruption("runtime control receipt digest fields differ")
                sections = receipt["changed_sections"]
                if not isinstance(sections, list) or len(sections) > 2 or any(not isinstance(section, str) or section not in {"global_policy", "tenant_learning"} for section in sections) or _json_dump(sections) != row["changed_sections_json"]:
                    raise ExecutionRepositoryCorruption("runtime control receipt sections differ")
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
        try:
            raw = row["state_json"]
            if not isinstance(raw, str) or len(raw) > learning.MAX_STATE_BYTES:
                raise learning.RuntimeLearningError("optimizer storage bound differs")
            state = _json_object(raw, "learning optimizer")
            if learning.digest(state) != row["state_digest"]:
                raise learning.RuntimeLearningError("optimizer digest differs")
            return learning.validate_state(state)
        except (ExecutionRepositoryCorruption, ValueError, TypeError, RecursionError, OverflowError) as exc:
            prior = hashlib.sha256(str(row["state_json"]).encode()).hexdigest()
            return learning.quarantine_state(seed, reason=str(exc), prior_digest=prior)

    def _save_learning_state_locked(
        self, identity: dict[str, Any], state: dict[str, Any], previous: sqlite3.Row | None,
        instant: datetime, *, maintenance: bool = False,
    ) -> int:
        learning.validate_state(state)
        version = 1 if previous is None else int(previous["version"]) + 1
        self._connection.execute(
            """INSERT INTO ai_execution_learning_state(
                   namespace, tenant_id, scope_id, partition_id, task_class, model_selection_digest,
                   version, state_digest, state_json, updated_at, maintenance_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(namespace, tenant_id, scope_id, partition_id) DO UPDATE SET
                   version = excluded.version, state_digest = excluded.state_digest,
                   state_json = excluded.state_json, updated_at = excluded.updated_at,
                   maintenance_at = excluded.maintenance_at""",
            (self.namespace, identity["tenant_id"], identity["scope_id"], identity["partition_id"],
             identity["task_class"], identity["model_selection_digest"], version,
             learning.digest(state), _json_dump(state), instant.isoformat(),
             instant.isoformat() if maintenance else (None if previous is None else previous["maintenance_at"])),
        )
        return version

    def _record_runtime_outcome_locked(
        self, execution: AIExecution, result: AIExecutionResult, instant: datetime
    ) -> dict[str, Any]:
        """Called inside the terminal transaction; never trusts caller rewards."""
        existing = self._connection.execute(
            """SELECT * FROM ai_execution_learning_outcome
               WHERE namespace = ? AND execution_id = ?""",
            (self.namespace, execution.execution_id),
        ).fetchone()
        if existing is not None:
            if existing["request_digest"] != execution.request.identity_digest or existing["result_digest"] != learning.digest(result.as_dict()):
                raise ExecutionRepositoryConflict("runtime learning outcome identity differs")
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
        try:
            policy = self._learning_policy_locked(tenant_id, scope_id)["policy"]
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
        if policy["enabled"] and observation["trainable"] and capacity:
            state = self._learning_state_locked(row, seed=seed)
            try:
                state, trained = learning.learn_outcome(state, observation, policy, seed=seed)
            except (learning.RuntimeLearningError, ArithmeticError, ValueError) as exc:
                state = learning.quarantine_state(seed, reason=f"optimizer update: {type(exc).__name__}")
            self._save_learning_state_locked(observation, state, row, instant)
            learning_status = "trained" if trained else "optimizer_quarantined"
        elif not capacity:
            learning_status = "partition_capacity"
        elif not policy["enabled"] and learning_status == "observed":
            learning_status = "disabled"
        elif not observation["trainable"] and learning_status == "observed":
            learning_status = "audit_only"

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
                    "learning_status": learning_status, "totals_health": "quarantined"}
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
                "recorded": True, "deduplicated": False, "trained": trained, "learning_status": learning_status}

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

    def runtime_learning_snapshot(
        self, *, tenant_id: str, scope_id: str = "tenant", limit: int = 20
    ) -> dict[str, Any]:
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ExecutionRepositoryError("learning snapshot limit must be in [1, 100]")
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
                   ORDER BY updated_at DESC, partition_id LIMIT ?""",
                (self.namespace, tenant_id, scope_id, limit),
            ).fetchall()
            partitions = []
            for row in rows:
                seed = f"{self.namespace}:{tenant_id}:{scope_id}:{row['partition_id']}"
                state = self._learning_state_locked(row, seed=seed)
                partitions.append({"partition_id": row["partition_id"], "task_class": row["task_class"],
                    "model_selection_digest": row["model_selection_digest"], "state_version": int(row["version"]),
                    "last_updated_at": row["updated_at"], **learning.state_readiness(state, policy)})
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
            return {"schema_version": "skeleton.runtime.learning.snapshot.v1", "tenant_id": tenant_id,
                "scope_id": scope_id, "policy": policy, "policy_version": configuration["version"],
                "totals": totals, "totals_health": totals_health,
                "observations": None if totals is None else totals["outcomes"], "partitions": partitions,
                "recent_outcomes": recent, "recent_outcome_errors": recent_outcome_errors,
                "model": {"kind": "bounded_online_mlp", "architecture": [12, 16, 8, 3], "optimizer": "adam",
                    "parameter_count": learning.PARAMETER_COUNT, "outputs": list(learning.OUTPUT_NAMES),
                    "latency_reference_seconds": learning.LATENCY_REFERENCE_SECONDS,
                    "labels": "canonical operational telemetry; not creative quality or verified correctness"},
                "limits": {"returned_partitions": len(partitions), "returned_outcomes": len(recent),
                    "max_optimizer_updates_per_outcome": 1 + policy["replay_steps"],
                    "partition_limit": policy["partition_limit"], "replay_capacity": policy["replay_capacity"]}}

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
                result = learning.recommend(state, configuration["policy"], features, allowed_rounds=allowed_rounds,
                    requested_rounds=requested_rounds, pressure=pressure)
                return {**result, **identity, "policy_version": configuration["version"],
                    "state_version": 0 if row is None else int(row["version"])}
        except learning.RuntimeLearningError as exc:
            raise ExecutionRepositoryError(str(exc)) from exc

    def runtime_learning_maintenance(
        self, *, tenant_id: str, scope_id: str = "tenant", max_partitions: int = 4, now: datetime | None = None
    ) -> dict[str, Any]:
        """Bounded idle replay/integrity work on this repository's existing state.

        Quarantined optimizer weights are discarded. Recovery uses at most four
        digest-checked canonical outcomes and returns to cold-start confidence.
        No provider model is trained, activated, selected, or promoted here.
        """
        tenant_id, scope_id = self._learning_scope(tenant_id, scope_id)
        if isinstance(max_partitions, bool) or not isinstance(max_partitions, int) or not 1 <= max_partitions <= 8:
            raise ExecutionRepositoryError("maintenance partition bound must be in [1, 8]")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                policy = self._learning_policy_locked(tenant_id, scope_id)["policy"]
                if not policy["enabled"]:
                    self._connection.execute("COMMIT")
                    return {"schema_version": "skeleton.runtime.learning.maintenance.v1", "tenant_id": tenant_id,
                        "scope_id": scope_id, "processed_partitions": 0, "partitions": [],
                        "deferred_reason": "learning_disabled", "external_model_work": False,
                        "completed_at": instant.isoformat()}
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
                    try:
                        if recovering:
                            old_quarantine = state["quarantine"]
                            candidate = learning.new_state(seed)
                            recent = self._connection.execute(
                                """SELECT * FROM ai_execution_learning_outcome
                                   WHERE namespace = ? AND tenant_id = ? AND scope_id = ? AND partition_id = ?
                                   ORDER BY observed_at DESC LIMIT 4""",
                                (self.namespace, tenant_id, scope_id, row["partition_id"]),
                            ).fetchall()
                            for outcome_row in reversed(recent):
                                observation = _json_object(outcome_row["observation_json"], "learning recovery outcome")
                                if learning.digest(observation) != outcome_row["observation_digest"]:
                                    raise ExecutionRepositoryCorruption("learning recovery outcome digest differs")
                                canonical_execution = self.get(outcome_row["execution_id"])
                                canonical_result = self.result(outcome_row["execution_id"])
                                if canonical_result is None or canonical_execution.request.identity_digest != outcome_row["request_digest"] or learning.digest(canonical_result.as_dict()) != outcome_row["result_digest"]:
                                    raise ExecutionRepositoryCorruption("learning recovery terminal identity differs")
                                candidate, _ = learning.learn_outcome(candidate, observation, {**policy, "replay_steps": 0}, seed=seed)
                            candidate["recovery"] = {"prior_quarantine": old_quarantine, "recovered_at": instant.isoformat()}
                            state = candidate
                        else:
                            state = learning.replay_maintenance(state, policy, max_updates=2)
                    except (ExecutionRepositoryError, ValueError, TypeError, ArithmeticError, RecursionError) as exc:
                        maintenance_error = type(exc).__name__
                        state = learning.quarantine_state(seed, reason=f"maintenance: {type(exc).__name__}")
                    self._save_learning_state_locked(dict(row), state, row, instant, maintenance=True)
                    entries.append({"partition_id": row["partition_id"], "recovered": recovering and not state["quarantined"],
                        "optimizer_updates": max(0, int(state["optimizer"]["step"]) - (0 if recovering else updates_before)),
                        "maintenance_error": maintenance_error, **learning.state_readiness(state, policy)})
                self._connection.execute("COMMIT")
                return {"schema_version": "skeleton.runtime.learning.maintenance.v1", "tenant_id": tenant_id,
                    "scope_id": scope_id, "processed_partitions": len(entries), "partitions": entries,
                    "quarantined_partitions": sum(entry["quarantined"] for entry in entries),
                    "external_model_work": False, "completed_at": instant.isoformat()}
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
