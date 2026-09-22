"""Transactional SQLite execution-audit persistence for Jeeves.

The in-memory execution audit proves ordering and tamper evidence while a process
is alive. Consequential tools need one stronger property: once the runtime has
observed a real side effect, that fact must survive process death *before* the
next ordinary runtime checkpoint.

``SQLiteExecutionAuditStore`` is API-compatible with the in-memory audit store
used by ``RuntimeEpistemicGuard``. Each ``append`` is one ``BEGIN IMMEDIATE``
transaction with ``synchronous=FULL``. Sequence assignment and previous-hash
selection therefore happen under the same database write lock as insertion.

The database stores canonical JSON payloads plus the complete chain envelope. A
reader reconstructs normal ``ExecutionAuditEntry`` values and the existing
replay verifiers remain authoritative; SQLite is persistence, not a competing
semantic verifier.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

from .execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ExecutionAuditCheckpoint,
    ExecutionAuditEntry,
    ExecutionAuditError,
    ExecutionReplayVerifier,
    GENESIS_HASH,
    ReplayReport,
)
from .types import json_safe, positive_int, require_id, stable_fingerprint, stable_id


_DURABLE_AUDIT_SCHEMA_VERSION = 1
_SAFE_RUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$")


class DurableAuditError(ExecutionAuditError):
    """Raised when the durable audit database cannot preserve the contract."""


class SQLiteExecutionAuditLedger:
    """One logical run ledger backed by a transactional SQLite store."""

    def __init__(self, store: "SQLiteExecutionAuditStore", run_id: str) -> None:
        self._store = store
        self.run_id = store._run_id(run_id)

    def append(
        self,
        kind: AuditEventKind,
        payload: Mapping[str, Any],
        *,
        operation_id: str | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        at: float | None = None,
    ) -> ExecutionAuditEntry:
        if not isinstance(kind, AuditEventKind):
            kind = AuditEventKind(str(kind))
        if not isinstance(severity, AuditSeverity):
            severity = AuditSeverity(str(severity))
        if operation_id is not None:
            operation_id = require_id("operation_id", operation_id)
        clean_payload = json_safe(dict(payload))
        payload_json = self._store._encode(clean_payload)
        explicit_timestamp = None if at is None else float(at)
        if explicit_timestamp is not None and (
            not math.isfinite(explicit_timestamp) or explicit_timestamp < 0
        ):
            raise DurableAuditError("audit timestamp must be finite and non-negative")

        conn = self._store._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Auto-generated wall-clock time is sampled only after the SQLite
                # write lock is held. Sampling before BEGIN IMMEDIATE lets a
                # concurrent caller wait with an older timestamp and then append
                # after a newer event, creating a false clock-regression failure.
                timestamp = (
                    self._store._now()
                    if explicit_timestamp is None
                    else explicit_timestamp
                )
                last = conn.execute(
                    """
                    SELECT sequence,event_hash,at
                    FROM jeeves_execution_audit
                    WHERE run_id=? ORDER BY sequence DESC LIMIT 1
                    """,
                    (self.run_id,),
                ).fetchone()
                if last is None:
                    sequence = 1
                    previous_hash = GENESIS_HASH
                else:
                    sequence = int(last["sequence"]) + 1
                    previous_hash = str(last["event_hash"])
                    if timestamp + 1e-12 < float(last["at"]):
                        raise DurableAuditError(
                            "durable audit wall clock moved backwards"
                        )
                if sequence > self._store.maximum_events_per_run:
                    raise DurableAuditError("durable execution audit capacity exhausted")

                event_id = stable_id(
                    "audit_event",
                    {
                        "run": self.run_id,
                        "sequence": sequence,
                        "kind": kind.value,
                        "operation": operation_id,
                        "previous": previous_hash,
                        "payload": clean_payload,
                    },
                )
                envelope = {
                    "event_id": event_id,
                    "run_id": self.run_id,
                    "operation_id": operation_id,
                    "sequence": sequence,
                    "kind": kind.value,
                    "severity": severity.value,
                    "at": timestamp,
                    "previous_hash": previous_hash,
                    "payload": clean_payload,
                }
                event_hash = stable_fingerprint(envelope)
                conn.execute(
                    """
                    INSERT INTO jeeves_execution_audit(
                        run_id,sequence,event_id,operation_id,kind,severity,at,
                        previous_hash,payload_json,event_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.run_id,
                        sequence,
                        event_id,
                        operation_id,
                        kind.value,
                        severity.value,
                        timestamp,
                        previous_hash,
                        payload_json,
                        event_hash,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

        return ExecutionAuditEntry(
            event_id=event_id,
            run_id=self.run_id,
            operation_id=operation_id,
            sequence=sequence,
            kind=kind,
            severity=severity,
            at=timestamp,
            previous_hash=previous_hash,
            payload=clean_payload,
            event_hash=event_hash,
        )

    def entries(self) -> tuple[ExecutionAuditEntry, ...]:
        conn = self._store._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM jeeves_execution_audit
                WHERE run_id=? ORDER BY sequence ASC
                """,
                (self.run_id,),
            ).fetchall()
        finally:
            conn.close()
        return tuple(self._store._entry(row) for row in rows)

    def operation_entries(self, operation_id: str) -> tuple[ExecutionAuditEntry, ...]:
        operation_id = require_id("operation_id", operation_id)
        conn = self._store._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM jeeves_execution_audit
                WHERE run_id=? AND operation_id=? ORDER BY sequence ASC
                """,
                (self.run_id, operation_id),
            ).fetchall()
        finally:
            conn.close()
        return tuple(self._store._entry(row) for row in rows)

    @property
    def head_hash(self) -> str:
        conn = self._store._connect()
        try:
            row = conn.execute(
                """
                SELECT event_hash FROM jeeves_execution_audit
                WHERE run_id=? ORDER BY sequence DESC LIMIT 1
                """,
                (self.run_id,),
            ).fetchone()
            return GENESIS_HASH if row is None else str(row["event_hash"])
        finally:
            conn.close()

    @property
    def event_count(self) -> int:
        conn = self._store._connect()
        try:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM jeeves_execution_audit WHERE run_id=?",
                    (self.run_id,),
                ).fetchone()[0]
            )
        finally:
            conn.close()

    def checkpoint(self) -> ExecutionAuditCheckpoint:
        entries = self.entries()
        counts = Counter(item.kind.value for item in entries)
        payload = {
            "run_id": self.run_id,
            "event_count": len(entries),
            "head_hash": entries[-1].event_hash if entries else GENESIS_HASH,
            "first_sequence": entries[0].sequence if entries else 0,
            "last_sequence": entries[-1].sequence if entries else 0,
            "first_at": entries[0].at if entries else None,
            "last_at": entries[-1].at if entries else None,
            "kind_counts": dict(sorted(counts.items())),
        }
        return ExecutionAuditCheckpoint(
            **payload,
            checkpoint_fingerprint=stable_fingerprint(payload),
        )

    def export(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(entry.to_dict() for entry in self.entries())


class SQLiteExecutionAuditStore:
    """Process-independent execution-audit registry.

    Multiple processes may construct stores for the same file. SQLite's write
    lock serializes append sequence allocation; the chain therefore has one
    durable head per run even across workers.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        maximum_events_per_run: int = 1_000_000,
        maximum_payload_bytes: int = 4 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise ValueError("SQLiteExecutionAuditStore requires durable path")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.maximum_events_per_run = positive_int(
            "maximum_events_per_run",
            maximum_events_per_run,
            maximum=20_000_000,
        )
        self.maximum_payload_bytes = positive_int(
            "maximum_payload_bytes",
            maximum_payload_bytes,
            maximum=128 * 1024 * 1024,
        )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._init_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            timeout=15.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _initialize(self) -> None:
        with self._init_lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jeeves_execution_audit (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        event_id TEXT NOT NULL UNIQUE,
                        operation_id TEXT,
                        kind TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        at REAL NOT NULL,
                        previous_hash TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE,
                        PRIMARY KEY(run_id, sequence),
                        CHECK(sequence >= 1)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_jeeves_audit_operation
                    ON jeeves_execution_audit(run_id, operation_id, sequence)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jeeves_execution_audit_meta (
                        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                        schema_version INTEGER NOT NULL
                    )
                    """
                )
                row = conn.execute(
                    "SELECT schema_version FROM jeeves_execution_audit_meta WHERE singleton=1"
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO jeeves_execution_audit_meta(singleton,schema_version) VALUES(1,?)",
                        (_DURABLE_AUDIT_SCHEMA_VERSION,),
                    )
                elif int(row[0]) != _DURABLE_AUDIT_SCHEMA_VERSION:
                    raise DurableAuditError(
                        "unsupported durable execution-audit schema version"
                    )
            finally:
                conn.close()

    def get_or_create(self, run_id: str) -> SQLiteExecutionAuditLedger:
        return SQLiteExecutionAuditLedger(self, self._run_id(run_id))

    def get(self, run_id: str) -> SQLiteExecutionAuditLedger | None:
        run_id = self._run_id(run_id)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM jeeves_execution_audit WHERE run_id=? LIMIT 1",
                (run_id,),
            ).fetchone()
        finally:
            conn.close()
        return None if row is None else SQLiteExecutionAuditLedger(self, run_id)

    def remove(self, run_id: str) -> bool:
        run_id = self._run_id(run_id)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "DELETE FROM jeeves_execution_audit WHERE run_id=?",
                    (run_id,),
                )
                changed = cursor.rowcount > 0
                conn.execute("COMMIT")
                return changed
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def runs(self) -> tuple[str, ...]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT run_id FROM jeeves_execution_audit ORDER BY run_id"
            ).fetchall()
            return tuple(str(row[0]) for row in rows)
        finally:
            conn.close()

    def verify(
        self,
        run_id: str,
        *,
        expected_checkpoint: ExecutionAuditCheckpoint | None = None,
        require_finalized_operations: bool = False,
    ) -> ReplayReport:
        run_id = self._run_id(run_id)
        ledger = self.get(run_id)
        entries = () if ledger is None else ledger.entries()
        return ExecutionReplayVerifier().verify(
            entries,
            expected_run_id=run_id,
            expected_checkpoint=expected_checkpoint,
            require_finalized_operations=require_finalized_operations,
        )

    def _now(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value) or value < 0:
            raise DurableAuditError("clock returned invalid audit timestamp")
        return value

    def _encode(self, payload: Any) -> str:
        text = json.dumps(
            json_safe(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(text.encode("utf-8")) > self.maximum_payload_bytes:
            raise DurableAuditError("durable audit payload exceeds configured bound")
        return text

    @staticmethod
    def _entry(row: sqlite3.Row) -> ExecutionAuditEntry:
        return ExecutionAuditEntry(
            event_id=str(row["event_id"]),
            run_id=str(row["run_id"]),
            operation_id=row["operation_id"],
            sequence=int(row["sequence"]),
            kind=AuditEventKind(str(row["kind"])),
            severity=AuditSeverity(str(row["severity"])),
            at=float(row["at"]),
            previous_hash=str(row["previous_hash"]),
            payload=json.loads(str(row["payload_json"])),
            event_hash=str(row["event_hash"]),
        )

    @staticmethod
    def _run_id(value: str) -> str:
        value = require_id("run_id", value)
        if len(value) > 256 or not _SAFE_RUN.fullmatch(value):
            raise ValueError("run_id is not safe for durable audit storage")
        return value