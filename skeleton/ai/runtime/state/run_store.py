"""Durable run, step, and checkpoint persistence for restart-safe execution.

The store is deliberately provider-neutral and stdlib-only. It uses SQLite
transactions as the authoritative coordination boundary, leases to prevent two
workers from owning the same live run, idempotency keys to protect external
side effects during replay, and explicit checkpoints to make crash recovery
observable rather than implicit.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
DEFAULT_MAX_PAYLOAD_BYTES = 1_048_576
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")


class RunStoreError(RuntimeError):
    """Base error for durable run-store operations."""


class RunNotFound(RunStoreError):
    """Raised when a requested run does not exist."""


class StateConflict(RunStoreError):
    """Raised when a concurrent or stale state transition is rejected."""


class InvalidTransition(RunStoreError):
    """Raised when a state-machine transition is not allowed."""


class PayloadTooLarge(RunStoreError):
    """Raised before oversized state is persisted."""


class SchemaVersionError(RunStoreError):
    """Raised when the database schema is newer or otherwise unsupported."""


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


class StepStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def terminal(self) -> bool:
        return self is not self.RUNNING


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: RunStatus
    revision: int
    input: Any
    output: Any | None
    error: str | None
    worker_id: str | None
    lease_until: float | None
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class StepRecord:
    run_id: str
    step_id: str
    sequence: int
    status: StepStatus
    kind: str
    payload: Any
    result: Any | None
    error: str | None
    effect_key: str | None
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    run_id: str
    revision: int
    after_step_id: str | None
    state_version: int
    state: Any
    created_at: float


@dataclass(frozen=True)
class ResumeState:
    run: RunRecord
    checkpoint: CheckpointRecord | None
    replay_steps: tuple[StepRecord, ...]


_ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class SQLiteRunStore:
    """Transactional SQLite persistence for resumable runs.

    A store instance opens short-lived database connections per operation. That
    keeps restart behavior honest and permits multiple processes to coordinate
    through SQLite locking rather than process-local state.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if isinstance(max_payload_bytes, bool) or not isinstance(max_payload_bytes, int):
            raise ValueError("max_payload_bytes must be a positive integer")
        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be a positive integer")
        if not callable(clock):
            raise TypeError("clock must be callable")

        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise ValueError("SQLiteRunStore requires a durable filesystem path")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._max_payload_bytes = max_payload_bytes
        self._clock = clock
        self._init_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            timeout=10.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _initialize(self) -> None:
        with self._init_lock:
            conn = self._connect()
            try:
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                if version not in {0, SCHEMA_VERSION}:
                    raise SchemaVersionError(
                        f"unsupported run-store schema version {version}; "
                        f"expected {SCHEMA_VERSION}"
                    )
                if version == SCHEMA_VERSION:
                    self._verify_schema(conn)
                    return

                try:
                    conn.executescript(
                        f"""
                        BEGIN IMMEDIATE;

                        CREATE TABLE runs (
                            run_id TEXT PRIMARY KEY,
                            status TEXT NOT NULL,
                            revision INTEGER NOT NULL DEFAULT 0,
                            input_json TEXT NOT NULL,
                            output_json TEXT,
                            error TEXT,
                            worker_id TEXT,
                            lease_until REAL,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL,
                            CHECK (status IN ('pending','running','succeeded','failed','cancelled')),
                            CHECK (revision >= 0)
                        );

                        CREATE TABLE steps (
                            run_id TEXT NOT NULL,
                            step_id TEXT NOT NULL,
                            sequence INTEGER NOT NULL,
                            status TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            result_json TEXT,
                            error TEXT,
                            effect_key TEXT,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL,
                            PRIMARY KEY (run_id, step_id),
                            UNIQUE (run_id, sequence),
                            UNIQUE (run_id, effect_key),
                            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
                            CHECK (status IN ('running','succeeded','failed','skipped')),
                            CHECK (sequence >= 1)
                        );

                        CREATE TABLE checkpoints (
                            checkpoint_id TEXT PRIMARY KEY,
                            run_id TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            after_step_id TEXT,
                            state_version INTEGER NOT NULL,
                            state_json TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            UNIQUE (run_id, revision),
                            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
                            FOREIGN KEY (run_id, after_step_id)
                                REFERENCES steps(run_id, step_id),
                            CHECK (revision >= 1),
                            CHECK (state_version >= 1)
                        );

                        CREATE INDEX idx_steps_run_sequence
                            ON steps(run_id, sequence);
                        CREATE INDEX idx_runs_recovery
                            ON runs(status, lease_until, updated_at);

                        PRAGMA user_version = {SCHEMA_VERSION};
                        COMMIT;
                        """
                    )
                except Exception:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
                self._verify_schema(conn)
            finally:
                conn.close()

    @staticmethod
    def _verify_schema(conn: sqlite3.Connection) -> None:
        required = {"runs", "steps", "checkpoints"}
        found = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(required - found)
        if missing:
            raise SchemaVersionError(
                "run-store schema is incomplete: " + ", ".join(missing)
            )

    def _now(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value):
            raise RunStoreError("clock returned a non-finite timestamp")
        return value

    @staticmethod
    def _identifier(value: str, field: str) -> str:
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError(f"{field} must be 1-128 safe identifier characters")
        return value

    @staticmethod
    def _duration(value: float, field: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{field} must be finite and > 0")
        try:
            duration = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be finite and > 0") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"{field} must be finite and > 0")
        return duration

    def _json(self, value: Any, field: str) -> str:
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be finite JSON data") from exc
        if len(encoded.encode("utf-8")) > self._max_payload_bytes:
            raise PayloadTooLarge(
                f"{field} exceeds {self._max_payload_bytes} encoded bytes"
            )
        return encoded

    @staticmethod
    def _decode(value: str | None) -> Any | None:
        if value is None:
            return None
        return json.loads(value)

    def _run_from_row(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            revision=int(row["revision"]),
            input=self._decode(row["input_json"]),
            output=self._decode(row["output_json"]),
            error=row["error"],
            worker_id=row["worker_id"],
            lease_until=row["lease_until"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def _step_from_row(self, row: sqlite3.Row) -> StepRecord:
        return StepRecord(
            run_id=row["run_id"],
            step_id=row["step_id"],
            sequence=int(row["sequence"]),
            status=StepStatus(row["status"]),
            kind=row["kind"],
            payload=self._decode(row["payload_json"]),
            result=self._decode(row["result_json"]),
            error=row["error"],
            effect_key=row["effect_key"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def _checkpoint_from_row(self, row: sqlite3.Row) -> CheckpointRecord:
        return CheckpointRecord(
            checkpoint_id=row["checkpoint_id"],
            run_id=row["run_id"],
            revision=int(row["revision"]),
            after_step_id=row["after_step_id"],
            state_version=int(row["state_version"]),
            state=self._decode(row["state_json"]),
            created_at=float(row["created_at"]),
        )

    @staticmethod
    def _require_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(f"unknown run: {run_id}")
        return row

    @staticmethod
    def _require_revision(row: sqlite3.Row, expected_revision: int | None) -> None:
        if expected_revision is None:
            return
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("expected_revision must be a non-negative integer")
        if expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        actual = int(row["revision"])
        if actual != expected_revision:
            raise StateConflict(
                f"stale run revision: expected {expected_revision}, found {actual}"
            )

    @staticmethod
    def _require_live_owner(
        row: sqlite3.Row,
        worker_id: str,
        now: float,
    ) -> None:
        if RunStatus(row["status"]) is not RunStatus.RUNNING:
            raise InvalidTransition("operation requires a running run")
        if row["worker_id"] != worker_id:
            raise StateConflict("worker does not own this run")
        lease_until = row["lease_until"]
        if lease_until is None or float(lease_until) <= now:
            raise StateConflict("worker lease has expired")

    def create_run(self, run_id: str, input: Any | None = None) -> RunRecord:
        run_id = self._identifier(run_id, "run_id")
        input_json = self._json({} if input is None else input, "input")
        now = self._now()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO runs(
                        run_id,status,revision,input_json,created_at,updated_at
                    ) VALUES (?, 'pending', 0, ?, ?, ?)
                    """,
                    (run_id, input_json, now, now),
                )
                row = self._require_run(conn, run_id)
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise StateConflict(f"run already exists: {run_id}") from exc
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return self._run_from_row(row)

    def get_run(self, run_id: str) -> RunRecord:
        run_id = self._identifier(run_id, "run_id")
        conn = self._connect()
        try:
            return self._run_from_row(self._require_run(conn, run_id))
        finally:
            conn.close()

    def claim_run(
        self,
        run_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        expected_revision: int | None = None,
    ) -> RunRecord:
        run_id = self._identifier(run_id, "run_id")
        worker_id = self._identifier(worker_id, "worker_id")
        lease_seconds = self._duration(lease_seconds, "lease_seconds")
        now = self._now()
        lease_until = now + lease_seconds

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._require_run(conn, run_id)
                self._require_revision(row, expected_revision)
                status = RunStatus(row["status"])
                if status.terminal:
                    raise InvalidTransition(f"cannot claim terminal run: {status.value}")

                owner = row["worker_id"]
                current_lease = row["lease_until"]
                if (
                    status is RunStatus.RUNNING
                    and owner not in {None, worker_id}
                    and current_lease is not None
                    and float(current_lease) > now
                ):
                    raise StateConflict(
                        f"run is leased by another worker until {float(current_lease):.6f}"
                    )

                conn.execute(
                    """
                    UPDATE runs
                    SET status='running', worker_id=?, lease_until=?,
                        revision=revision+1, updated_at=?
                    WHERE run_id=?
                    """,
                    (worker_id, lease_until, now, run_id),
                )
                row = self._require_run(conn, run_id)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return self._run_from_row(row)

    def heartbeat(
        self,
        run_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        expected_revision: int | None = None,
    ) -> RunRecord:
        run_id = self._identifier(run_id, "run_id")
        worker_id = self._identifier(worker_id, "worker_id")
        lease_seconds = self._duration(lease_seconds, "lease_seconds")
        now = self._now()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._require_run(conn, run_id)
                self._require_revision(row, expected_revision)
                self._require_live_owner(row, worker_id, now)
                conn.execute(
                    """
                    UPDATE runs
                    SET lease_until=?, revision=revision+1, updated_at=?
                    WHERE run_id=?
                    """,
                    (now + lease_seconds, now, run_id),
                )
                row = self._require_run(conn, run_id)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return self._run_from_row(row)

    def transition_run(
        self,
        run_id: str,
        to_status: RunStatus | str,
        *,
        worker_id: str | None = None,
        expected_revision: int | None = None,
        output: Any | None = None,
        error: str | None = None,
    ) -> RunRecord:
        run_id = self._identifier(run_id, "run_id")
        try:
            target = RunStatus(to_status)
        except ValueError as exc:
            raise ValueError(f"unknown run status: {to_status!r}") from exc
        if worker_id is not None:
            worker_id = self._identifier(worker_id, "worker_id")
        output_json = None if output is None else self._json(output, "output")
        if error is not None and not isinstance(error, str):
            raise ValueError("error must be text or None")
        if error is not None and len(error) > 4096:
            raise ValueError("error must be at most 4096 characters")
        now = self._now()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._require_run(conn, run_id)
                self._require_revision(row, expected_revision)
                current = RunStatus(row["status"])
                if target not in _ALLOWED_TRANSITIONS[current]:
                    raise InvalidTransition(
                        f"invalid run transition {current.value} -> {target.value}"
                    )
                if current is RunStatus.RUNNING:
                    if worker_id is None:
                        raise StateConflict("terminal transition requires the owning worker")
                    self._require_live_owner(row, worker_id, now)
                if target is RunStatus.SUCCEEDED:
                    unfinished = conn.execute(
                        "SELECT 1 FROM steps WHERE run_id=? AND status='running' LIMIT 1",
                        (run_id,),
                    ).fetchone()
                    if unfinished is not None:
                        raise InvalidTransition(
                            "cannot succeed a run with unfinished steps"
                        )

                conn.execute(
                    """
                    UPDATE runs
                    SET status=?, output_json=?, error=?, worker_id=NULL,
                        lease_until=NULL, revision=revision+1, updated_at=?
                    WHERE run_id=?
                    """,
                    (target.value, output_json, error, now, run_id),
                )
                row = self._require_run(conn, run_id)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return self._run_from_row(row)

    def start_step(
        self,
        run_id: str,
        step_id: str,
        kind: str,
        *,
        worker_id: str,
        payload: Any | None = None,
        effect_key: str | None = None,
    ) -> StepRecord:
        run_id = self._identifier(run_id, "run_id")
        step_id = self._identifier(step_id, "step_id")
        kind = self._identifier(kind, "kind")
        worker_id = self._identifier(worker_id, "worker_id")
        if effect_key is not None:
            effect_key = self._identifier(effect_key, "effect_key")
        payload_json = self._json({} if payload is None else payload, "payload")
        now = self._now()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                run = self._require_run(conn, run_id)
                self._require_live_owner(run, worker_id, now)

                existing = conn.execute(
                    "SELECT * FROM steps WHERE run_id=? AND step_id=?",
                    (run_id, step_id),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["kind"] != kind
                        or existing["payload_json"] != payload_json
                        or existing["effect_key"] != effect_key
                    ):
                        raise StateConflict(
                            "step identity was reused with different semantics"
                        )
                    conn.execute("COMMIT")
                    return self._step_from_row(existing)

                if effect_key is not None:
                    prior_effect = conn.execute(
                        "SELECT * FROM steps WHERE run_id=? AND effect_key=?",
                        (run_id, effect_key),
                    ).fetchone()
                    if prior_effect is not None:
                        raise StateConflict(
                            "effect_key is already bound to another step"
                        )

                sequence = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM steps WHERE run_id=?",
                        (run_id,),
                    ).fetchone()[0]
                )
                conn.execute(
                    """
                    INSERT INTO steps(
                        run_id,step_id,sequence,status,kind,payload_json,
                        effect_key,created_at,updated_at
                    ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        step_id,
                        sequence,
                        kind,
                        payload_json,
                        effect_key,
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM steps WHERE run_id=? AND step_id=?",
                    (run_id, step_id),
                ).fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        assert row is not None
        return self._step_from_row(row)

    def finish_step(
        self,
        run_id: str,
        step_id: str,
        status: StepStatus | str,
        *,
        worker_id: str,
        result: Any | None = None,
        error: str | None = None,
    ) -> StepRecord:
        run_id = self._identifier(run_id, "run_id")
        step_id = self._identifier(step_id, "step_id")
        worker_id = self._identifier(worker_id, "worker_id")
        try:
            target = StepStatus(status)
        except ValueError as exc:
            raise ValueError(f"unknown step status: {status!r}") from exc
        if not target.terminal:
            raise InvalidTransition("finish_step requires a terminal step status")
        result_json = None if result is None else self._json(result, "result")
        if error is not None and (not isinstance(error, str) or len(error) > 4096):
            raise ValueError("error must be text of at most 4096 characters")
        now = self._now()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                run = self._require_run(conn, run_id)
                self._require_live_owner(run, worker_id, now)
                row = conn.execute(
                    "SELECT * FROM steps WHERE run_id=? AND step_id=?",
                    (run_id, step_id),
                ).fetchone()
                if row is None:
                    raise RunStoreError(f"unknown step: {step_id}")
                current = StepStatus(row["status"])
                if current.terminal:
                    if (
                        current is target
                        and row["result_json"] == result_json
                        and row["error"] == error
                    ):
                        conn.execute("COMMIT")
                        return self._step_from_row(row)
                    raise StateConflict("step is already terminal with different outcome")

                conn.execute(
                    """
                    UPDATE steps
                    SET status=?, result_json=?, error=?, updated_at=?
                    WHERE run_id=? AND step_id=?
                    """,
                    (target.value, result_json, error, now, run_id, step_id),
                )
                row = conn.execute(
                    "SELECT * FROM steps WHERE run_id=? AND step_id=?",
                    (run_id, step_id),
                ).fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        assert row is not None
        return self._step_from_row(row)

    def checkpoint(
        self,
        run_id: str,
        state: Any,
        *,
        worker_id: str,
        after_step_id: str | None = None,
        state_version: int = 1,
    ) -> CheckpointRecord:
        run_id = self._identifier(run_id, "run_id")
        worker_id = self._identifier(worker_id, "worker_id")
        if after_step_id is not None:
            after_step_id = self._identifier(after_step_id, "after_step_id")
        if isinstance(state_version, bool) or not isinstance(state_version, int) or state_version < 1:
            raise ValueError("state_version must be a positive integer")
        state_json = self._json(state, "checkpoint state")
        now = self._now()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                run = self._require_run(conn, run_id)
                self._require_live_owner(run, worker_id, now)

                boundary = 0
                if after_step_id is not None:
                    step = conn.execute(
                        "SELECT * FROM steps WHERE run_id=? AND step_id=?",
                        (run_id, after_step_id),
                    ).fetchone()
                    if step is None:
                        raise RunStoreError(f"unknown checkpoint step: {after_step_id}")
                    if StepStatus(step["status"]) not in {
                        StepStatus.SUCCEEDED,
                        StepStatus.SKIPPED,
                    }:
                        raise InvalidTransition(
                            "checkpoint boundary must follow a succeeded or skipped step"
                        )
                    boundary = int(step["sequence"])

                previous = conn.execute(
                    """
                    SELECT * FROM checkpoints
                    WHERE run_id=? ORDER BY revision DESC LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                if previous is not None:
                    previous_boundary = 0
                    if previous["after_step_id"] is not None:
                        previous_step = conn.execute(
                            "SELECT sequence FROM steps WHERE run_id=? AND step_id=?",
                            (run_id, previous["after_step_id"]),
                        ).fetchone()
                        if previous_step is None:
                            raise SchemaVersionError(
                                "checkpoint references a missing step"
                            )
                        previous_boundary = int(previous_step["sequence"])
                    if boundary < previous_boundary:
                        raise InvalidTransition(
                            "checkpoint boundary cannot move backwards"
                        )

                revision = 1 if previous is None else int(previous["revision"]) + 1
                checkpoint_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO checkpoints(
                        checkpoint_id,run_id,revision,after_step_id,
                        state_version,state_json,created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint_id,
                        run_id,
                        revision,
                        after_step_id,
                        state_version,
                        state_json,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM checkpoints WHERE checkpoint_id=?",
                    (checkpoint_id,),
                ).fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        assert row is not None
        return self._checkpoint_from_row(row)

    def resume_state(self, run_id: str) -> ResumeState:
        run_id = self._identifier(run_id, "run_id")
        conn = self._connect()
        try:
            run_row = self._require_run(conn, run_id)
            checkpoint_row = conn.execute(
                """
                SELECT * FROM checkpoints
                WHERE run_id=? ORDER BY revision DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()

            boundary = 0
            if checkpoint_row is not None and checkpoint_row["after_step_id"] is not None:
                step = conn.execute(
                    "SELECT sequence FROM steps WHERE run_id=? AND step_id=?",
                    (run_id, checkpoint_row["after_step_id"]),
                ).fetchone()
                if step is None:
                    raise SchemaVersionError("checkpoint references a missing step")
                boundary = int(step["sequence"])

            rows = conn.execute(
                """
                SELECT * FROM steps
                WHERE run_id=? AND sequence>?
                ORDER BY sequence ASC
                """,
                (run_id, boundary),
            ).fetchall()
            return ResumeState(
                run=self._run_from_row(run_row),
                checkpoint=(
                    None
                    if checkpoint_row is None
                    else self._checkpoint_from_row(checkpoint_row)
                ),
                replay_steps=tuple(self._step_from_row(row) for row in rows),
            )
        finally:
            conn.close()

    def list_recoverable(self, *, limit: int = 100) -> tuple[RunRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 10_000:
            raise ValueError("limit must be an integer from 1 to 10000")
        now = self._now()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM runs
                WHERE status='pending'
                   OR (status='running' AND (lease_until IS NULL OR lease_until<=?))
                ORDER BY updated_at ASC, run_id ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            return tuple(self._run_from_row(row) for row in rows)
        finally:
            conn.close()

    def list_steps(self, run_id: str) -> tuple[StepRecord, ...]:
        run_id = self._identifier(run_id, "run_id")
        conn = self._connect()
        try:
            self._require_run(conn, run_id)
            rows = conn.execute(
                "SELECT * FROM steps WHERE run_id=? ORDER BY sequence ASC",
                (run_id,),
            ).fetchall()
            return tuple(self._step_from_row(row) for row in rows)
        finally:
            conn.close()
