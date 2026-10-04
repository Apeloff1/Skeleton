"""Durable effect-boundary journal for deferred AI execution.

The admission plane answers whether an operation may run. This journal answers a
separate question: whether a particular admitted operation has crossed the
handler effect boundary. A durable "started" row is written before the handler
is entered. If a process disappears before a terminal receipt is committed, a
later executor can see the unresolved row and fail closed instead of repeating
an effect whose outcome is unknown.

The journal is intentionally payload-minimal. It stores the content-bound
invocation envelope, handler identity, and terminal replay material, but never
the original request payload.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Protocol

from .contracts import canonical_json, sha256_json


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_STATES = {"started", "succeeded", "failed"}


class DeferredJournalError(RuntimeError):
    """Base error for durable deferred-execution journal failures."""


class DeferredJournalConflict(DeferredJournalError):
    """Raised when an operation identity is replayed with different material."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _canonical_object(value: object, name: str) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    encoded = canonical_json(dict(value))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError(f"{name} must encode a JSON object")
    return decoded, encoded


@dataclass(frozen=True, slots=True)
class DeferredJournalRecord:
    """One content-bound journal row."""

    operation_id: str
    fingerprint: str
    invocation_json: str
    handler_identity: str
    state: str
    terminal_json: str | None
    record_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            _sha256(self.fingerprint, "fingerprint"),
        )
        object.__setattr__(
            self,
            "handler_identity",
            _text(self.handler_identity, "handler_identity"),
        )
        if self.state not in _STATES:
            raise ValueError("unsupported deferred journal state")

        try:
            invocation = json.loads(self.invocation_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invocation_json must be valid JSON") from exc
        if not isinstance(invocation, dict):
            raise ValueError("invocation_json must encode an object")
        if canonical_json(invocation) != self.invocation_json:
            raise ValueError("invocation_json must be canonical JSON")

        if self.state == "started":
            if self.terminal_json is not None:
                raise ValueError("started journal row cannot have terminal payload")
        else:
            if self.terminal_json is None:
                raise ValueError("terminal journal row requires terminal payload")
            try:
                terminal = json.loads(self.terminal_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("terminal_json must be valid JSON") from exc
            if not isinstance(terminal, dict):
                raise ValueError("terminal_json must encode an object")
            if canonical_json(terminal) != self.terminal_json:
                raise ValueError("terminal_json must be canonical JSON")

        object.__setattr__(
            self,
            "record_digest",
            _sha256(self.record_digest, "record_digest"),
        )
        if self.record_digest != sha256_json(self.digest_material()):
            raise DeferredJournalConflict("deferred journal record digest mismatch")

    @property
    def invocation(self) -> dict[str, Any]:
        value = json.loads(self.invocation_json)
        assert isinstance(value, dict)
        return value

    @property
    def terminal(self) -> dict[str, Any] | None:
        if self.terminal_json is None:
            return None
        value = json.loads(self.terminal_json)
        assert isinstance(value, dict)
        return value

    def digest_material(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "fingerprint": self.fingerprint,
            "invocation": self.invocation,
            "handler_identity": self.handler_identity,
            "state": self.state,
            "terminal": self.terminal,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.digest_material(),
            "record_digest": self.record_digest,
        }


def _record(
    *,
    operation_id: str,
    fingerprint: str,
    invocation: Mapping[str, Any],
    handler_identity: str,
    state: str,
    terminal: Mapping[str, Any] | None,
) -> DeferredJournalRecord:
    operation_id = _text(operation_id, "operation_id")
    fingerprint = _sha256(fingerprint, "fingerprint")
    handler_identity = _text(handler_identity, "handler_identity")
    if state not in _STATES:
        raise ValueError("unsupported deferred journal state")
    invocation_object, invocation_json = _canonical_object(
        invocation,
        "invocation",
    )
    terminal_object: dict[str, Any] | None
    terminal_json: str | None
    if terminal is None:
        terminal_object = None
        terminal_json = None
    else:
        terminal_object, terminal_json = _canonical_object(
            terminal,
            "terminal",
        )
    if state == "started" and terminal_object is not None:
        raise ValueError("started journal row cannot have terminal payload")
    if state != "started" and terminal_object is None:
        raise ValueError("terminal journal row requires terminal payload")

    material = {
        "schema_version": 1,
        "operation_id": operation_id,
        "fingerprint": fingerprint,
        "invocation": invocation_object,
        "handler_identity": handler_identity,
        "state": state,
        "terminal": terminal_object,
    }
    return DeferredJournalRecord(
        operation_id=operation_id,
        fingerprint=fingerprint,
        invocation_json=invocation_json,
        handler_identity=handler_identity,
        state=state,
        terminal_json=terminal_json,
        record_digest=sha256_json(material),
    )


class DeferredExecutionJournal(Protocol):
    """Storage contract consumed by DeferredExecutor."""

    def load(self, operation_id: str) -> DeferredJournalRecord | None:
        ...

    def records(self) -> tuple[DeferredJournalRecord, ...]:
        ...

    def record_started(
        self,
        *,
        operation_id: str,
        fingerprint: str,
        invocation: Mapping[str, Any],
        handler_identity: str,
    ) -> tuple[DeferredJournalRecord, bool]:
        ...

    def record_terminal(
        self,
        *,
        operation_id: str,
        fingerprint: str,
        state: str,
        terminal: Mapping[str, Any],
    ) -> DeferredJournalRecord:
        ...




class SqliteDeferredExecutionJournal:
    """SQLite-backed at-most-once effect-boundary journal.

    A file-backed database is required. ":memory:" is rejected because this
    component exists specifically to survive process loss.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS deferred_execution_journal (
        operation_id TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        invocation_json TEXT NOT NULL,
        handler_identity TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('started', 'succeeded', 'failed')),
        terminal_json TEXT,
        record_digest TEXT NOT NULL,
        CHECK (
            (state = 'started' AND terminal_json IS NULL)
            OR
            (state IN ('succeeded', 'failed') AND terminal_json IS NOT NULL)
        )
    )
    """

    def __init__(self, path: str | Path) -> None:
        raw_path = str(path)
        if not raw_path or raw_path == ":memory:":
            raise ValueError("durable deferred journal requires a file path")
        self.path = Path(raw_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
            if mode is None or str(mode[0]).lower() != "wal":
                raise DeferredJournalError(
                    "durable deferred journal requires SQLite WAL mode"
                )
            conn.execute(self._SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            isolation_level=None,
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DeferredJournalRecord:
        return DeferredJournalRecord(
            operation_id=row["operation_id"],
            fingerprint=row["fingerprint"],
            invocation_json=row["invocation_json"],
            handler_identity=row["handler_identity"],
            state=row["state"],
            terminal_json=row["terminal_json"],
            record_digest=row["record_digest"],
        )

    @classmethod
    def _load_locked(
        cls,
        conn: sqlite3.Connection,
        operation_id: str,
    ) -> DeferredJournalRecord | None:
        row = conn.execute(
            """
            SELECT
                operation_id,
                fingerprint,
                invocation_json,
                handler_identity,
                state,
                terminal_json,
                record_digest
            FROM deferred_execution_journal
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        return cls._from_row(row)

    def load(self, operation_id: str) -> DeferredJournalRecord | None:
        operation_id = _text(operation_id, "operation_id")
        with self._connect() as conn:
            return self._load_locked(conn, operation_id)

    def records(self) -> tuple[DeferredJournalRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    operation_id,
                    fingerprint,
                    invocation_json,
                    handler_identity,
                    state,
                    terminal_json,
                    record_digest
                FROM deferred_execution_journal
                ORDER BY operation_id
                """
            ).fetchall()
            return tuple(self._from_row(row) for row in rows)

    def record_started(
        self,
        *,
        operation_id: str,
        fingerprint: str,
        invocation: Mapping[str, Any],
        handler_identity: str,
    ) -> tuple[DeferredJournalRecord, bool]:
        candidate = _record(
            operation_id=operation_id,
            fingerprint=fingerprint,
            invocation=invocation,
            handler_identity=handler_identity,
            state="started",
            terminal=None,
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._load_locked(conn, candidate.operation_id)
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO deferred_execution_journal (
                            operation_id,
                            fingerprint,
                            invocation_json,
                            handler_identity,
                            state,
                            terminal_json,
                            record_digest
                        ) VALUES (?, ?, ?, ?, 'started', NULL, ?)
                        """,
                        (
                            candidate.operation_id,
                            candidate.fingerprint,
                            candidate.invocation_json,
                            candidate.handler_identity,
                            candidate.record_digest,
                        ),
                    )
                    conn.execute("COMMIT")
                    return candidate, True

                if (
                    existing.fingerprint != candidate.fingerprint
                    or existing.invocation_json != candidate.invocation_json
                    or existing.handler_identity != candidate.handler_identity
                ):
                    raise DeferredJournalConflict(
                        "deferred operation journal identity collision"
                    )
                conn.execute("COMMIT")
                return existing, False
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def record_terminal(
        self,
        *,
        operation_id: str,
        fingerprint: str,
        state: str,
        terminal: Mapping[str, Any],
    ) -> DeferredJournalRecord:
        if state not in {"succeeded", "failed"}:
            raise ValueError("terminal state must be succeeded or failed")
        operation_id = _text(operation_id, "operation_id")
        fingerprint = _sha256(fingerprint, "fingerprint")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._load_locked(conn, operation_id)
                if existing is None:
                    raise DeferredJournalConflict(
                        "terminal deferred journal update has no started record"
                    )
                if existing.fingerprint != fingerprint:
                    raise DeferredJournalConflict(
                        "terminal deferred journal fingerprint mismatch"
                    )
                candidate = _record(
                    operation_id=existing.operation_id,
                    fingerprint=existing.fingerprint,
                    invocation=existing.invocation,
                    handler_identity=existing.handler_identity,
                    state=state,
                    terminal=terminal,
                )
                if existing.state == "started":
                    conn.execute(
                        """
                        UPDATE deferred_execution_journal
                        SET state = ?, terminal_json = ?, record_digest = ?
                        WHERE operation_id = ?
                        """,
                        (
                            candidate.state,
                            candidate.terminal_json,
                            candidate.record_digest,
                            operation_id,
                        ),
                    )
                    conn.execute("COMMIT")
                    return candidate

                if existing == candidate:
                    conn.execute("COMMIT")
                    return existing
                raise DeferredJournalConflict(
                    "terminal deferred journal state already differs"
                )
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def snapshot(self) -> dict[str, object]:
        rows = [record.as_dict() for record in self.records()]
        payload = {
            "schema_version": 1,
            "records": rows,
        }
        return {
            **payload,
            "snapshot_digest": sha256_json(payload),
        }


__all__ = [
    "DeferredExecutionJournal",
    "DeferredJournalConflict",
    "DeferredJournalError",
    "DeferredJournalRecord",
    "SqliteDeferredExecutionJournal",
]
