"""Restart-safe long-horizon autonomy for VOL-018.

This module is a persistence/control boundary, not a second worker runtime.
It gives long-running agent work a durable lifecycle over SQLite, exact
checkpoints, one-shot resume tokens, deadline/step/retry enforcement, and one
human-control API that consumes the existing P1 HumanControlDecision receipt.

Execution remains owned by the existing agent/swarm runtimes. This scheduler
only decides which durable operation may be resumed or claimed next.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping, Sequence

from skeleton.automation.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes


SCHEMA = "skeleton.long_horizon_autonomy.v1"


class LongHorizonError(RuntimeError):
    """Long-horizon state, persistence, or control evidence is invalid."""


class LongHorizonConflict(LongHorizonError):
    """The requested transition conflicts with current durable state."""


class ReauthorizationRequired(LongHorizonConflict):
    """Goal or authority identity changed and requires explicit human override."""


class LongRunningState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    RETRY_WAIT = "retry_wait"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    EXPIRED = "expired"


TERMINAL_STATES = frozenset(
    {
        LongRunningState.COMPLETED,
        LongRunningState.FAILED,
        LongRunningState.CANCELLED,
        LongRunningState.INTERRUPTED,
        LongRunningState.EXPIRED,
    }
)
RESUMABLE_STATES = frozenset(
    {
        LongRunningState.WAITING,
        LongRunningState.RETRY_WAIT,
        LongRunningState.PAUSED,
    }
)
DUE_STATES = frozenset(
    {
        LongRunningState.QUEUED,
        LongRunningState.WAITING,
        LongRunningState.RETRY_WAIT,
    }
)


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise LongHorizonError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise LongHorizonError(f"{field} must be a canonical non-empty token")
    return normalized


def _sha256(value: object, field: str) -> str:
    token = _token(value, field, maximum=64)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise LongHorizonError(f"{field} must be a lowercase SHA-256 digest")
    return token


def _finite(
    value: object,
    field: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LongHorizonError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise LongHorizonError(f"{field} must be finite numeric")
    if positive and result <= 0:
        raise LongHorizonError(f"{field} must be greater than zero")
    if non_negative and result < 0:
        raise LongHorizonError(f"{field} must be non-negative")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LongHorizonError(f"{field} must be a positive integer")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LongHorizonError(f"{field} must be a non-negative integer")
    return value


def _canonical_json(value: object, field: str) -> str:
    try:
        return canonical_json_bytes(value).decode("utf-8")
    except CanonicalContractError as exc:
        raise LongHorizonError(f"{field} must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value, "digest payload").encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class LongRunningOperation:
    operation_id: str
    execution_id: str
    agent_id: str
    objective_digest: str
    authority_digest: str
    state: LongRunningState = LongRunningState.QUEUED
    version: int = 1
    attempts: int = 0
    max_attempts: int = 8
    step_budget: int = 256
    steps_used: int = 0
    deadline_at: float = 0.0
    next_run_at: float | None = None
    checkpoint_sequence: int | None = None
    last_control_receipt_digest: str | None = None
    error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        for field in ("objective_digest", "authority_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        try:
            object.__setattr__(self, "state", LongRunningState(self.state))
        except ValueError as exc:
            raise LongHorizonError("invalid long-running state") from exc
        object.__setattr__(self, "version", _positive_int(self.version, "version"))
        object.__setattr__(
            self,
            "attempts",
            _non_negative_int(self.attempts, "attempts"),
        )
        object.__setattr__(
            self,
            "max_attempts",
            _positive_int(self.max_attempts, "max_attempts"),
        )
        object.__setattr__(
            self,
            "step_budget",
            _positive_int(self.step_budget, "step_budget"),
        )
        object.__setattr__(
            self,
            "steps_used",
            _non_negative_int(self.steps_used, "steps_used"),
        )
        if self.attempts > self.max_attempts:
            raise LongHorizonError("attempts exceeds max_attempts")
        if self.steps_used > self.step_budget:
            raise LongHorizonError("steps_used exceeds step_budget")
        deadline = _finite(
            self.deadline_at,
            "deadline_at",
            non_negative=True,
        )
        object.__setattr__(self, "deadline_at", deadline)
        if self.next_run_at is not None:
            object.__setattr__(
                self,
                "next_run_at",
                _finite(
                    self.next_run_at,
                    "next_run_at",
                    non_negative=True,
                ),
            )
        if self.checkpoint_sequence is not None:
            object.__setattr__(
                self,
                "checkpoint_sequence",
                _positive_int(
                    self.checkpoint_sequence,
                    "checkpoint_sequence",
                ),
            )
        if self.last_control_receipt_digest is not None:
            object.__setattr__(
                self,
                "last_control_receipt_digest",
                _sha256(
                    self.last_control_receipt_digest,
                    "last_control_receipt_digest",
                ),
            )
        if self.error is not None:
            object.__setattr__(
                self,
                "error",
                _token(self.error, "error", maximum=4096),
            )
        created = _finite(self.created_at, "created_at", non_negative=True)
        updated = _finite(self.updated_at, "updated_at", non_negative=True)
        if updated < created:
            raise LongHorizonError("updated_at precedes created_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def remaining_steps(self) -> int:
        return self.step_budget - self.steps_used

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "objective_digest": self.objective_digest,
            "authority_digest": self.authority_digest,
        }

    def payload(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "state": self.state.value,
            "version": self.version,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "step_budget": self.step_budget,
            "steps_used": self.steps_used,
            "deadline_at": self.deadline_at,
            "next_run_at": self.next_run_at,
            "checkpoint_sequence": self.checkpoint_sequence,
            "last_control_receipt_digest": self.last_control_receipt_digest,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @property
    def identity_digest(self) -> str:
        return _digest(self.identity_payload())

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class Checkpoint:
    operation_id: str
    sequence: int
    operation_version: int
    objective_digest: str
    authority_digest: str
    payload_digest: str
    created_at: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _token(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "sequence",
            _positive_int(self.sequence, "sequence"),
        )
        object.__setattr__(
            self,
            "operation_version",
            _positive_int(self.operation_version, "operation_version"),
        )
        object.__setattr__(
            self,
            "objective_digest",
            _sha256(self.objective_digest, "objective_digest"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        object.__setattr__(
            self,
            "payload_digest",
            _sha256(self.payload_digest, "payload_digest"),
        )
        object.__setattr__(
            self,
            "created_at",
            _finite(self.created_at, "created_at", non_negative=True),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "checkpoint",
                "operation_id": self.operation_id,
                "sequence": self.sequence,
                "operation_version": self.operation_version,
                "objective_digest": self.objective_digest,
                "authority_digest": self.authority_digest,
                "payload_digest": self.payload_digest,
                "created_at": self.created_at,
            }
        )


@dataclass(frozen=True, slots=True)
class ResumeToken:
    token_digest: str
    operation_id: str
    checkpoint_sequence: int
    operation_version: int
    objective_digest: str
    authority_digest: str
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "token_digest",
            _sha256(self.token_digest, "token_digest"),
        )
        object.__setattr__(
            self,
            "operation_id",
            _token(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "checkpoint_sequence",
            _positive_int(
                self.checkpoint_sequence,
                "checkpoint_sequence",
            ),
        )
        object.__setattr__(
            self,
            "operation_version",
            _positive_int(self.operation_version, "operation_version"),
        )
        object.__setattr__(
            self,
            "objective_digest",
            _sha256(self.objective_digest, "objective_digest"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        issued = _finite(self.issued_at, "issued_at", non_negative=True)
        expires = _finite(self.expires_at, "expires_at", positive=True)
        if expires <= issued:
            raise LongHorizonError("resume token expiry must follow issue time")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)


@dataclass(frozen=True, slots=True)
class OverrideDecision:
    accepted: bool
    operation_id: str
    action: HumanControlAction
    human_receipt_digest: str
    previous_state: LongRunningState
    next_state: LongRunningState
    previous_version: int
    next_version: int
    reason: str
    observed_at: float
    decision_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise LongHorizonError("accepted must be boolean")
        object.__setattr__(
            self,
            "operation_id",
            _token(self.operation_id, "operation_id"),
        )
        try:
            object.__setattr__(
                self,
                "action",
                HumanControlAction(self.action),
            )
            object.__setattr__(
                self,
                "previous_state",
                LongRunningState(self.previous_state),
            )
            object.__setattr__(
                self,
                "next_state",
                LongRunningState(self.next_state),
            )
        except ValueError as exc:
            raise LongHorizonError("invalid override enum value") from exc
        object.__setattr__(
            self,
            "human_receipt_digest",
            _sha256(
                self.human_receipt_digest,
                "human_receipt_digest",
            ),
        )
        object.__setattr__(
            self,
            "previous_version",
            _positive_int(self.previous_version, "previous_version"),
        )
        object.__setattr__(
            self,
            "next_version",
            _positive_int(self.next_version, "next_version"),
        )
        if self.accepted and self.next_version != self.previous_version + 1:
            raise LongHorizonError(
                "accepted override must advance operation version once"
            )
        if not self.accepted and self.next_version != self.previous_version:
            raise LongHorizonError(
                "rejected override cannot advance operation version"
            )
        object.__setattr__(self, "reason", _token(self.reason, "reason"))
        object.__setattr__(
            self,
            "observed_at",
            _finite(self.observed_at, "observed_at", non_negative=True),
        )
        object.__setattr__(
            self,
            "decision_digest",
            _sha256(self.decision_digest, "decision_digest"),
        )


_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS long_horizon_operation (
    operation_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    objective_digest TEXT NOT NULL,
    authority_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    step_budget INTEGER NOT NULL,
    steps_used INTEGER NOT NULL,
    deadline_at REAL NOT NULL,
    next_run_at REAL,
    checkpoint_sequence INTEGER,
    last_control_receipt_digest TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS long_horizon_checkpoint (
    operation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    operation_version INTEGER NOT NULL,
    objective_digest TEXT NOT NULL,
    authority_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (operation_id, sequence),
    FOREIGN KEY (operation_id)
        REFERENCES long_horizon_operation(operation_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS long_horizon_resume_token (
    token_digest TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    checkpoint_sequence INTEGER NOT NULL,
    operation_version INTEGER NOT NULL,
    objective_digest TEXT NOT NULL,
    authority_digest TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    consumed_at REAL,
    FOREIGN KEY (operation_id)
        REFERENCES long_horizon_operation(operation_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS long_horizon_override (
    decision_digest TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    human_receipt_digest TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_state TEXT NOT NULL,
    next_state TEXT NOT NULL,
    previous_version INTEGER NOT NULL,
    next_version INTEGER NOT NULL,
    reason TEXT NOT NULL,
    observed_at REAL NOT NULL,
    FOREIGN KEY (operation_id)
        REFERENCES long_horizon_operation(operation_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_long_horizon_due
ON long_horizon_operation(state, next_run_at, deadline_at);

CREATE INDEX IF NOT EXISTS idx_long_horizon_checkpoint_latest
ON long_horizon_checkpoint(operation_id, sequence DESC);
"""


class SqliteLongHorizonStore:
    """Durable operation/checkpoint/resume/override storage."""

    def __init__(self, path: str | Path, *, timeout_seconds: float = 10.0) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise LongHorizonError(
                "long-horizon store requires a filesystem path"
            )
        self.timeout_seconds = _finite(
            timeout_seconds,
            "timeout_seconds",
            positive=True,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    @staticmethod
    def _operation(row: sqlite3.Row) -> LongRunningOperation:
        return LongRunningOperation(
            operation_id=row["operation_id"],
            execution_id=row["execution_id"],
            agent_id=row["agent_id"],
            objective_digest=row["objective_digest"],
            authority_digest=row["authority_digest"],
            state=LongRunningState(row["state"]),
            version=int(row["version"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            step_budget=int(row["step_budget"]),
            steps_used=int(row["steps_used"]),
            deadline_at=float(row["deadline_at"]),
            next_run_at=(
                None
                if row["next_run_at"] is None
                else float(row["next_run_at"])
            ),
            checkpoint_sequence=(
                None
                if row["checkpoint_sequence"] is None
                else int(row["checkpoint_sequence"])
            ),
            last_control_receipt_digest=row["last_control_receipt_digest"],
            error=row["error"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def create(self, operation: LongRunningOperation) -> LongRunningOperation:
        if not isinstance(operation, LongRunningOperation):
            raise TypeError("operation must be LongRunningOperation")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                    (operation.operation_id,),
                ).fetchone()
                if existing is not None:
                    current = self._operation(existing)
                    if current != operation:
                        raise LongHorizonConflict(
                            "operation id is already registered differently"
                        )
                    conn.execute("COMMIT")
                    return current
                conn.execute(
                    """
                    INSERT INTO long_horizon_operation (
                        operation_id, execution_id, agent_id,
                        objective_digest, authority_digest, state, version,
                        attempts, max_attempts, step_budget, steps_used,
                        deadline_at, next_run_at, checkpoint_sequence,
                        last_control_receipt_digest, error,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation.operation_id,
                        operation.execution_id,
                        operation.agent_id,
                        operation.objective_digest,
                        operation.authority_digest,
                        operation.state.value,
                        operation.version,
                        operation.attempts,
                        operation.max_attempts,
                        operation.step_budget,
                        operation.steps_used,
                        operation.deadline_at,
                        operation.next_run_at,
                        operation.checkpoint_sequence,
                        operation.last_control_receipt_digest,
                        operation.error,
                        operation.created_at,
                        operation.updated_at,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get(operation.operation_id)

    def get(self, operation_id: str) -> LongRunningOperation:
        operation = _token(operation_id, "operation_id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                (operation,),
            ).fetchone()
        if row is None:
            raise KeyError(operation)
        return self._operation(row)

    @staticmethod
    def _guard_goal(
        operation: LongRunningOperation,
        *,
        objective_digest: str,
        authority_digest: str,
    ) -> None:
        objective = _sha256(objective_digest, "objective_digest")
        authority = _sha256(authority_digest, "authority_digest")
        if (
            operation.objective_digest != objective
            or operation.authority_digest != authority
        ):
            raise ReauthorizationRequired(
                "objective or authority identity changed"
            )

    def assert_goal(
        self,
        operation_id: str,
        *,
        objective_digest: str,
        authority_digest: str,
    ) -> LongRunningOperation:
        operation = self.get(operation_id)
        self._guard_goal(
            operation,
            objective_digest=objective_digest,
            authority_digest=authority_digest,
        )
        return operation

    def claim_due(
        self,
        *,
        now: float,
        limit: int = 1,
    ) -> tuple[LongRunningOperation, ...]:
        observed = _finite(now, "now", non_negative=True)
        bounded = _positive_int(limit, "limit")
        claimed: list[LongRunningOperation] = []
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM long_horizon_operation
                    WHERE state IN (?, ?, ?)
                      AND (next_run_at IS NULL OR next_run_at <= ?)
                    ORDER BY COALESCE(next_run_at, created_at), created_at, operation_id
                    LIMIT ?
                    """,
                    (
                        LongRunningState.QUEUED.value,
                        LongRunningState.WAITING.value,
                        LongRunningState.RETRY_WAIT.value,
                        observed,
                        bounded * 4,
                    ),
                ).fetchall()
                for row in rows:
                    if len(claimed) >= bounded:
                        break
                    current = self._operation(row)
                    if current.deadline_at and observed >= current.deadline_at:
                        conn.execute(
                            """
                            UPDATE long_horizon_operation
                            SET state = ?, version = version + 1,
                                error = ?, updated_at = ?
                            WHERE operation_id = ? AND version = ?
                            """,
                            (
                                LongRunningState.EXPIRED.value,
                                "deadline_exceeded",
                                observed,
                                current.operation_id,
                                current.version,
                            ),
                        )
                        continue
                    if current.steps_used >= current.step_budget:
                        conn.execute(
                            """
                            UPDATE long_horizon_operation
                            SET state = ?, version = version + 1,
                                error = ?, updated_at = ?
                            WHERE operation_id = ? AND version = ?
                            """,
                            (
                                LongRunningState.FAILED.value,
                                "step_budget_exhausted",
                                observed,
                                current.operation_id,
                                current.version,
                            ),
                        )
                        continue
                    if current.attempts >= current.max_attempts:
                        conn.execute(
                            """
                            UPDATE long_horizon_operation
                            SET state = ?, version = version + 1,
                                error = ?, updated_at = ?
                            WHERE operation_id = ? AND version = ?
                            """,
                            (
                                LongRunningState.FAILED.value,
                                "attempt_budget_exhausted",
                                observed,
                                current.operation_id,
                                current.version,
                            ),
                        )
                        continue
                    cursor = conn.execute(
                        """
                        UPDATE long_horizon_operation
                        SET state = ?, version = version + 1,
                            attempts = attempts + 1,
                            next_run_at = NULL, error = NULL, updated_at = ?
                        WHERE operation_id = ? AND version = ?
                        """,
                        (
                            LongRunningState.RUNNING.value,
                            observed,
                            current.operation_id,
                            current.version,
                        ),
                    )
                    if cursor.rowcount != 1:
                        continue
                    loaded = conn.execute(
                        "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                        (current.operation_id,),
                    ).fetchone()
                    assert loaded is not None
                    claimed.append(self._operation(loaded))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return tuple(claimed)

    def transition(
        self,
        operation_id: str,
        *,
        expected_states: Sequence[LongRunningState],
        next_state: LongRunningState,
        now: float,
        next_run_at: float | None = None,
        error: str | None = None,
        step_increment: int = 0,
        control_receipt_digest: str | None = None,
    ) -> LongRunningOperation:
        operation = _token(operation_id, "operation_id")
        expected = tuple(LongRunningState(item) for item in expected_states)
        if not expected:
            raise LongHorizonError("expected_states must not be empty")
        target = LongRunningState(next_state)
        observed = _finite(now, "now", non_negative=True)
        increment = _non_negative_int(step_increment, "step_increment")
        scheduled = (
            None
            if next_run_at is None
            else _finite(next_run_at, "next_run_at", non_negative=True)
        )
        if scheduled is not None and scheduled < observed:
            raise LongHorizonError("next_run_at cannot be in the past")
        normalized_error = None
        if error is not None:
            normalized_error = _token(error, "error", maximum=4096)
        receipt = None
        if control_receipt_digest is not None:
            receipt = _sha256(
                control_receipt_digest,
                "control_receipt_digest",
            )

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                    (operation,),
                ).fetchone()
                if row is None:
                    raise KeyError(operation)
                current = self._operation(row)
                if current.state not in expected:
                    raise LongHorizonConflict(
                        f"state {current.state.value} cannot transition to {target.value}"
                    )
                if current.terminal:
                    raise LongHorizonConflict(
                        "terminal operation cannot transition"
                    )
                steps_used = current.steps_used + increment
                if steps_used > current.step_budget:
                    raise LongHorizonConflict("step budget would be exceeded")
                cursor = conn.execute(
                    """
                    UPDATE long_horizon_operation
                    SET state = ?, version = version + 1,
                        steps_used = ?, next_run_at = ?, error = ?,
                        last_control_receipt_digest =
                            COALESCE(?, last_control_receipt_digest),
                        updated_at = ?
                    WHERE operation_id = ? AND version = ?
                    """,
                    (
                        target.value,
                        steps_used,
                        scheduled,
                        normalized_error,
                        receipt,
                        observed,
                        operation,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LongHorizonConflict(
                        "operation changed during transition"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get(operation)

    def checkpoint(
        self,
        operation_id: str,
        payload: Mapping[str, Any],
        *,
        now: float,
    ) -> tuple[Checkpoint, LongRunningOperation]:
        operation = _token(operation_id, "operation_id")
        if not isinstance(payload, Mapping):
            raise LongHorizonError("checkpoint payload must be a mapping")
        observed = _finite(now, "now", non_negative=True)
        payload_json = _canonical_json(dict(payload), "checkpoint payload")
        payload_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                    (operation,),
                ).fetchone()
                if row is None:
                    raise KeyError(operation)
                current = self._operation(row)
                if current.terminal:
                    raise LongHorizonConflict(
                        "terminal operation cannot checkpoint"
                    )
                sequence_row = conn.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) AS sequence
                    FROM long_horizon_checkpoint
                    WHERE operation_id = ?
                    """,
                    (operation,),
                ).fetchone()
                sequence = int(sequence_row["sequence"]) + 1
                next_version = current.version + 1
                conn.execute(
                    """
                    INSERT INTO long_horizon_checkpoint (
                        operation_id, sequence, operation_version,
                        objective_digest, authority_digest,
                        payload_json, payload_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation,
                        sequence,
                        next_version,
                        current.objective_digest,
                        current.authority_digest,
                        payload_json,
                        payload_digest,
                        observed,
                    ),
                )
                cursor = conn.execute(
                    """
                    UPDATE long_horizon_operation
                    SET version = ?, checkpoint_sequence = ?, updated_at = ?
                    WHERE operation_id = ? AND version = ?
                    """,
                    (
                        next_version,
                        sequence,
                        observed,
                        operation,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LongHorizonConflict(
                        "operation changed during checkpoint"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        checkpoint = Checkpoint(
            operation_id=operation,
            sequence=sequence,
            operation_version=next_version,
            objective_digest=current.objective_digest,
            authority_digest=current.authority_digest,
            payload_digest=payload_digest,
            created_at=observed,
        )
        return checkpoint, self.get(operation)

    def load_checkpoint(
        self,
        operation_id: str,
        sequence: int | None = None,
    ) -> tuple[Checkpoint, dict[str, Any]]:
        operation = _token(operation_id, "operation_id")
        with self._connect() as conn:
            if sequence is None:
                row = conn.execute(
                    """
                    SELECT * FROM long_horizon_checkpoint
                    WHERE operation_id = ?
                    ORDER BY sequence DESC
                    LIMIT 1
                    """,
                    (operation,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM long_horizon_checkpoint
                    WHERE operation_id = ? AND sequence = ?
                    """,
                    (operation, _positive_int(sequence, "sequence")),
                ).fetchone()
        if row is None:
            raise KeyError(f"{operation}:checkpoint")
        raw = row["payload_json"]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LongHorizonError("persisted checkpoint JSON is invalid") from exc
        if not isinstance(payload, dict):
            raise LongHorizonError("persisted checkpoint root must be an object")
        digest = hashlib.sha256(
            _canonical_json(payload, "checkpoint payload").encode("utf-8")
        ).hexdigest()
        if digest != row["payload_digest"]:
            raise LongHorizonError("checkpoint payload digest mismatch")
        checkpoint = Checkpoint(
            operation_id=row["operation_id"],
            sequence=int(row["sequence"]),
            operation_version=int(row["operation_version"]),
            objective_digest=row["objective_digest"],
            authority_digest=row["authority_digest"],
            payload_digest=row["payload_digest"],
            created_at=float(row["created_at"]),
        )
        return checkpoint, payload

    def issue_resume_token(
        self,
        operation_id: str,
        *,
        now: float,
        expires_at: float,
    ) -> ResumeToken:
        operation = self.get(operation_id)
        observed = _finite(now, "now", non_negative=True)
        expiry = _finite(expires_at, "expires_at", positive=True)
        if expiry <= observed:
            raise LongHorizonError("resume token must expire in the future")
        if operation.state not in RESUMABLE_STATES:
            raise LongHorizonConflict(
                "resume token requires paused/waiting/retry state"
            )
        if operation.checkpoint_sequence is None:
            raise LongHorizonConflict(
                "resume token requires a durable checkpoint"
            )
        token_payload = {
            "schema": SCHEMA,
            "kind": "resume-token",
            "operation_id": operation.operation_id,
            "checkpoint_sequence": operation.checkpoint_sequence,
            "operation_version": operation.version,
            "objective_digest": operation.objective_digest,
            "authority_digest": operation.authority_digest,
            "issued_at": observed,
            "expires_at": expiry,
        }
        token = ResumeToken(
            token_digest=_digest(token_payload),
            operation_id=operation.operation_id,
            checkpoint_sequence=operation.checkpoint_sequence,
            operation_version=operation.version,
            objective_digest=operation.objective_digest,
            authority_digest=operation.authority_digest,
            issued_at=observed,
            expires_at=expiry,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO long_horizon_resume_token (
                    token_digest, operation_id, checkpoint_sequence,
                    operation_version, objective_digest, authority_digest,
                    issued_at, expires_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    token.token_digest,
                    token.operation_id,
                    token.checkpoint_sequence,
                    token.operation_version,
                    token.objective_digest,
                    token.authority_digest,
                    token.issued_at,
                    token.expires_at,
                ),
            )
        return token

    def consume_resume_token(
        self,
        token: ResumeToken,
        *,
        now: float,
        objective_digest: str,
        authority_digest: str,
    ) -> LongRunningOperation:
        if not isinstance(token, ResumeToken):
            raise TypeError("token must be ResumeToken")
        observed = _finite(now, "now", non_negative=True)
        objective = _sha256(objective_digest, "objective_digest")
        authority = _sha256(authority_digest, "authority_digest")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                token_row = conn.execute(
                    """
                    SELECT * FROM long_horizon_resume_token
                    WHERE token_digest = ?
                    """,
                    (token.token_digest,),
                ).fetchone()
                if token_row is None:
                    raise LongHorizonConflict("unknown resume token")
                if token_row["consumed_at"] is not None:
                    raise LongHorizonConflict("resume token already consumed")
                if observed >= float(token_row["expires_at"]):
                    raise LongHorizonConflict("resume token expired")
                persisted = ResumeToken(
                    token_digest=token_row["token_digest"],
                    operation_id=token_row["operation_id"],
                    checkpoint_sequence=int(token_row["checkpoint_sequence"]),
                    operation_version=int(token_row["operation_version"]),
                    objective_digest=token_row["objective_digest"],
                    authority_digest=token_row["authority_digest"],
                    issued_at=float(token_row["issued_at"]),
                    expires_at=float(token_row["expires_at"]),
                )
                if persisted != token:
                    raise LongHorizonConflict(
                        "resume token does not match persisted identity"
                    )
                row = conn.execute(
                    "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                    (token.operation_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(token.operation_id)
                operation = self._operation(row)
                self._guard_goal(
                    operation,
                    objective_digest=objective,
                    authority_digest=authority,
                )
                if (
                    token.objective_digest != objective
                    or token.authority_digest != authority
                ):
                    raise ReauthorizationRequired(
                        "resume token goal identity is stale"
                    )
                if operation.version != token.operation_version:
                    raise LongHorizonConflict(
                        "resume token operation version is stale"
                    )
                if operation.checkpoint_sequence != token.checkpoint_sequence:
                    raise LongHorizonConflict(
                        "resume token checkpoint is stale"
                    )
                if operation.state not in RESUMABLE_STATES:
                    raise LongHorizonConflict(
                        "operation is not in resumable state"
                    )
                cursor = conn.execute(
                    """
                    UPDATE long_horizon_operation
                    SET state = ?, version = version + 1,
                        next_run_at = NULL, error = NULL, updated_at = ?
                    WHERE operation_id = ? AND version = ?
                    """,
                    (
                        LongRunningState.QUEUED.value,
                        observed,
                        operation.operation_id,
                        operation.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LongHorizonConflict(
                        "operation changed while consuming resume token"
                    )
                conn.execute(
                    """
                    UPDATE long_horizon_resume_token
                    SET consumed_at = ?
                    WHERE token_digest = ? AND consumed_at IS NULL
                    """,
                    (observed, token.token_digest),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get(token.operation_id)

    def apply_human_control(
        self,
        decision: HumanControlDecision,
        *,
        now: float,
    ) -> OverrideDecision:
        if not isinstance(decision, HumanControlDecision):
            raise TypeError("decision must be HumanControlDecision")
        observed = _finite(now, "now", non_negative=True)
        if not decision.accepted:
            raise LongHorizonConflict(
                "rejected human-control decision cannot mutate operation"
            )
        if observed >= decision.expires_at:
            raise LongHorizonConflict("human-control decision expired")
        receipt = decision.receipt_digest
        operation = self.get(decision.operation_id)
        if (
            operation.execution_id != decision.execution_id
            or operation.agent_id != decision.agent_id
        ):
            raise LongHorizonConflict(
                "human-control identity does not match operation"
            )
        if operation.authority_digest != decision.authority_digest:
            raise ReauthorizationRequired(
                "human-control authority does not match operation"
            )
        if operation.terminal:
            raise LongHorizonConflict(
                "terminal operation rejects human control"
            )

        if decision.action is HumanControlAction.PAUSE:
            target = LongRunningState.PAUSED
            reason = "human-pause"
        elif decision.action is HumanControlAction.RESUME:
            if operation.state is not LongRunningState.PAUSED:
                raise LongHorizonConflict(
                    "human resume requires paused operation"
                )
            target = LongRunningState.QUEUED
            reason = "human-resume"
        elif decision.action is HumanControlAction.INTERRUPT:
            target = LongRunningState.INTERRUPTED
            reason = "human-interrupt"
        elif decision.action is HumanControlAction.OVERRIDE:
            if decision.next_interrupted:
                target = LongRunningState.INTERRUPTED
                reason = "human-override-interrupt"
            elif decision.next_paused:
                target = LongRunningState.PAUSED
                reason = "human-override-pause"
            else:
                target = operation.state
                reason = "human-override-control-receipt"
        else:
            target = operation.state
            reason = "human-approval-control-receipt"

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                fresh_row = conn.execute(
                    "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                    (operation.operation_id,),
                ).fetchone()
                assert fresh_row is not None
                fresh = self._operation(fresh_row)
                if fresh.version != operation.version:
                    raise LongHorizonConflict(
                        "operation changed before human control applied"
                    )
                cursor = conn.execute(
                    """
                    UPDATE long_horizon_operation
                    SET state = ?, version = version + 1,
                        next_run_at = CASE WHEN ? = ? THEN NULL ELSE next_run_at END,
                        last_control_receipt_digest = ?,
                        error = CASE WHEN ? IN (?, ?) THEN ? ELSE error END,
                        updated_at = ?
                    WHERE operation_id = ? AND version = ?
                    """,
                    (
                        target.value,
                        target.value,
                        LongRunningState.QUEUED.value,
                        receipt,
                        target.value,
                        LongRunningState.INTERRUPTED.value,
                        LongRunningState.CANCELLED.value,
                        reason,
                        observed,
                        operation.operation_id,
                        operation.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LongHorizonConflict(
                        "operation changed while applying human control"
                    )
                next_version = operation.version + 1
                decision_payload = {
                    "schema": SCHEMA,
                    "kind": "override-decision",
                    "operation_id": operation.operation_id,
                    "action": decision.action.value,
                    "human_receipt_digest": receipt,
                    "previous_state": operation.state.value,
                    "next_state": target.value,
                    "previous_version": operation.version,
                    "next_version": next_version,
                    "reason": reason,
                }
                decision_digest = _digest(decision_payload)
                conn.execute(
                    """
                    INSERT INTO long_horizon_override (
                        decision_digest, operation_id, human_receipt_digest,
                        action, previous_state, next_state,
                        previous_version, next_version, reason, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision_digest,
                        operation.operation_id,
                        receipt,
                        decision.action.value,
                        operation.state.value,
                        target.value,
                        operation.version,
                        next_version,
                        reason,
                        observed,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return OverrideDecision(
            accepted=True,
            operation_id=operation.operation_id,
            action=decision.action,
            human_receipt_digest=receipt,
            previous_state=operation.state,
            next_state=target,
            previous_version=operation.version,
            next_version=operation.version + 1,
            reason=reason,
            observed_at=observed,
            decision_digest=decision_digest,
        )

    def reauthorize_goal(
        self,
        operation_id: str,
        *,
        objective_digest: str,
        authority_digest: str,
        decision: HumanControlDecision,
        now: float,
    ) -> LongRunningOperation:
        operation = self.get(operation_id)
        if not isinstance(decision, HumanControlDecision):
            raise TypeError("decision must be HumanControlDecision")
        observed = _finite(now, "now", non_negative=True)
        if (
            not decision.accepted
            or decision.action is not HumanControlAction.OVERRIDE
        ):
            raise ReauthorizationRequired(
                "goal change requires accepted human override"
            )
        if observed >= decision.expires_at:
            raise ReauthorizationRequired("human override expired")
        if (
            decision.operation_id != operation.operation_id
            or decision.execution_id != operation.execution_id
            or decision.agent_id != operation.agent_id
            or decision.authority_digest != operation.authority_digest
        ):
            raise ReauthorizationRequired(
                "human override does not bind current operation authority"
            )
        new_objective = _sha256(objective_digest, "objective_digest")
        new_authority = _sha256(authority_digest, "authority_digest")
        receipt = decision.receipt_digest

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM long_horizon_operation WHERE operation_id = ?",
                    (operation.operation_id,),
                ).fetchone()
                assert row is not None
                fresh = self._operation(row)
                if fresh.version != operation.version:
                    raise LongHorizonConflict(
                        "operation changed before goal reauthorization"
                    )
                if fresh.terminal:
                    raise LongHorizonConflict(
                        "terminal operation cannot be reauthorized"
                    )
                cursor = conn.execute(
                    """
                    UPDATE long_horizon_operation
                    SET objective_digest = ?, authority_digest = ?,
                        state = ?, version = version + 1,
                        next_run_at = NULL,
                        last_control_receipt_digest = ?,
                        error = NULL, updated_at = ?
                    WHERE operation_id = ? AND version = ?
                    """,
                    (
                        new_objective,
                        new_authority,
                        LongRunningState.QUEUED.value,
                        receipt,
                        observed,
                        operation.operation_id,
                        operation.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LongHorizonConflict(
                        "operation changed during goal reauthorization"
                    )
                decision_payload = {
                    "schema": SCHEMA,
                    "kind": "goal-reauthorization",
                    "operation_id": operation.operation_id,
                    "human_receipt_digest": receipt,
                    "previous_objective_digest": operation.objective_digest,
                    "next_objective_digest": new_objective,
                    "previous_authority_digest": operation.authority_digest,
                    "next_authority_digest": new_authority,
                    "previous_version": operation.version,
                    "next_version": operation.version + 1,
                }
                decision_digest = _digest(decision_payload)
                conn.execute(
                    """
                    INSERT INTO long_horizon_override (
                        decision_digest, operation_id, human_receipt_digest,
                        action, previous_state, next_state,
                        previous_version, next_version, reason, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision_digest,
                        operation.operation_id,
                        receipt,
                        HumanControlAction.OVERRIDE.value,
                        operation.state.value,
                        LongRunningState.QUEUED.value,
                        operation.version,
                        operation.version + 1,
                        "goal-authority-reauthorized",
                        observed,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get(operation.operation_id)


class PersistentLongHorizonScheduler:
    """Restart-safe scheduler over :class:`SqliteLongHorizonStore`."""

    def __init__(self, store: SqliteLongHorizonStore) -> None:
        if not isinstance(store, SqliteLongHorizonStore):
            raise TypeError("store must be SqliteLongHorizonStore")
        self.store = store

    def register(
        self,
        *,
        operation_id: str,
        execution_id: str,
        agent_id: str,
        objective_digest: str,
        authority_digest: str,
        now: float,
        deadline_at: float = 0.0,
        max_attempts: int = 8,
        step_budget: int = 256,
    ) -> LongRunningOperation:
        observed = _finite(now, "now", non_negative=True)
        deadline = _finite(
            deadline_at,
            "deadline_at",
            non_negative=True,
        )
        if deadline and deadline <= observed:
            raise LongHorizonError("deadline must be in the future")
        operation = LongRunningOperation(
            operation_id=operation_id,
            execution_id=execution_id,
            agent_id=agent_id,
            objective_digest=objective_digest,
            authority_digest=authority_digest,
            state=LongRunningState.QUEUED,
            version=1,
            attempts=0,
            max_attempts=max_attempts,
            step_budget=step_budget,
            steps_used=0,
            deadline_at=deadline,
            next_run_at=observed,
            created_at=observed,
            updated_at=observed,
        )
        return self.store.create(operation)

    def claim_due(
        self,
        *,
        now: float,
        limit: int = 1,
    ) -> tuple[LongRunningOperation, ...]:
        return self.store.claim_due(now=now, limit=limit)

    def checkpoint(
        self,
        operation_id: str,
        payload: Mapping[str, Any],
        *,
        now: float,
    ) -> Checkpoint:
        checkpoint, _operation = self.store.checkpoint(
            operation_id,
            payload,
            now=now,
        )
        return checkpoint

    def wait_until(
        self,
        operation_id: str,
        *,
        until: float,
        now: float,
        step_increment: int = 1,
    ) -> LongRunningOperation:
        return self.store.transition(
            operation_id,
            expected_states=(LongRunningState.RUNNING,),
            next_state=LongRunningState.WAITING,
            now=now,
            next_run_at=until,
            step_increment=step_increment,
        )

    def retry_after(
        self,
        operation_id: str,
        *,
        delay_s: float,
        error: str,
        now: float,
        step_increment: int = 1,
    ) -> LongRunningOperation:
        observed = _finite(now, "now", non_negative=True)
        delay = _finite(delay_s, "delay_s", positive=True)
        return self.store.transition(
            operation_id,
            expected_states=(LongRunningState.RUNNING,),
            next_state=LongRunningState.RETRY_WAIT,
            now=observed,
            next_run_at=observed + delay,
            error=error,
            step_increment=step_increment,
        )

    def complete(
        self,
        operation_id: str,
        *,
        now: float,
        step_increment: int = 1,
    ) -> LongRunningOperation:
        return self.store.transition(
            operation_id,
            expected_states=(LongRunningState.RUNNING,),
            next_state=LongRunningState.COMPLETED,
            now=now,
            step_increment=step_increment,
        )

    def fail(
        self,
        operation_id: str,
        *,
        error: str,
        now: float,
        step_increment: int = 1,
    ) -> LongRunningOperation:
        return self.store.transition(
            operation_id,
            expected_states=(LongRunningState.RUNNING,),
            next_state=LongRunningState.FAILED,
            now=now,
            error=error,
            step_increment=step_increment,
        )

    def cancel(
        self,
        operation_id: str,
        *,
        now: float,
    ) -> LongRunningOperation:
        operation = self.store.get(operation_id)
        if operation.terminal:
            return operation
        return self.store.transition(
            operation_id,
            expected_states=(operation.state,),
            next_state=LongRunningState.CANCELLED,
            now=now,
            error="cancelled",
        )

    def issue_resume_token(
        self,
        operation_id: str,
        *,
        now: float,
        expires_at: float,
    ) -> ResumeToken:
        return self.store.issue_resume_token(
            operation_id,
            now=now,
            expires_at=expires_at,
        )

    def resume(
        self,
        token: ResumeToken,
        *,
        now: float,
        objective_digest: str,
        authority_digest: str,
    ) -> LongRunningOperation:
        return self.store.consume_resume_token(
            token,
            now=now,
            objective_digest=objective_digest,
            authority_digest=authority_digest,
        )

    def apply_human_control(
        self,
        decision: HumanControlDecision,
        *,
        now: float,
    ) -> OverrideDecision:
        return self.store.apply_human_control(decision, now=now)

    def reauthorize_goal(
        self,
        operation_id: str,
        *,
        objective_digest: str,
        authority_digest: str,
        decision: HumanControlDecision,
        now: float,
    ) -> LongRunningOperation:
        return self.store.reauthorize_goal(
            operation_id,
            objective_digest=objective_digest,
            authority_digest=authority_digest,
            decision=decision,
            now=now,
        )


__all__ = [
    "SCHEMA",
    "Checkpoint",
    "DUE_STATES",
    "LongHorizonConflict",
    "LongHorizonError",
    "LongRunningOperation",
    "LongRunningState",
    "OverrideDecision",
    "PersistentLongHorizonScheduler",
    "RESUMABLE_STATES",
    "ReauthorizationRequired",
    "ResumeToken",
    "SqliteLongHorizonStore",
    "TERMINAL_STATES",
]
