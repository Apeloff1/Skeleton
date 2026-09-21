"""Durable operation state and transactional outbox reference store.

This module binds the canonical OperationEnvelope state machine to SQLite
without coupling it to HTTP, queues, or a particular stream transport.

Every accepted create/transition commits operation state and one outbox event in
the same SQLite transaction. A dispatcher can append that outbox event to the
canonical operation stream using the deterministic event_id, retry safely, then
acknowledge the outbox row. This provides a concrete reconciliation contract
between operation authority and resumable transport without making the transport
the owner of operation truth.
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

from skeleton.contracts.operation import (
    OperationContractError,
    OperationEnvelope,
    OperationState,
)
from skeleton.frontier.operation_stream import StreamEvent


class OperationStoreError(RuntimeError):
    """Base durable operation-store failure."""


class OperationStoreConflict(OperationStoreError):
    """A durable identity/version invariant was violated."""


class OperationStoreCorruptionError(OperationStoreError):
    """Persisted operation state cannot be interpreted safely."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise OperationStoreError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise OperationStoreError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise OperationStoreCorruptionError(f"{field} must be persisted as text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OperationStoreCorruptionError(
            f"{field} is not valid ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationStoreCorruptionError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _strict_json_object(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise OperationStoreCorruptionError("outbox payload must be persisted as text")

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite JSON constant: {value}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=unique_pairs,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise OperationStoreCorruptionError(
            "persisted outbox payload is invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise OperationStoreCorruptionError(
            "persisted outbox payload must be an object"
        )
    return payload


def _event_id(namespace: str, operation_id: str, version: int) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"skeleton-operation-outbox:{namespace}:{operation_id}:{version}",
        )
    )


@dataclass(frozen=True, slots=True)
class StoredOperation:
    envelope: OperationEnvelope
    version: int
    updated_at: datetime

    @property
    def terminal(self) -> bool:
        return self.envelope.terminal

    def as_dict(self) -> dict[str, Any]:
        payload = self.envelope.as_dict()
        payload["version"] = self.version
        payload["updated_at"] = self.updated_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class OperationOutboxEvent:
    outbox_id: str
    operation_id: str
    operation_version: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    published_at: datetime | None = None

    @property
    def published(self) -> bool:
        return self.published_at is not None

    def as_stream_event(self, sequence: int) -> StreamEvent:
        """Materialize the exact retry-stable transport event identity."""

        return StreamEvent(
            operation_id=self.operation_id,
            event_id=self.outbox_id,
            sequence=sequence,
            type=self.event_type,
            timestamp=self.created_at,
            payload=dict(self.payload),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "outbox_id": self.outbox_id,
            "operation_id": self.operation_id,
            "operation_version": self.operation_version,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "created_at": self.created_at.isoformat(),
            "published_at": (
                None if self.published_at is None else self.published_at.isoformat()
            ),
        }


class SQLiteOperationStore:
    """SQLite reference repository for authoritative operation state."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "operation_state",
    ) -> None:
        namespace = str(namespace).strip()
        if not namespace:
            raise ValueError("namespace must not be empty")
        self.namespace = namespace
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS operation_state (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    identity_digest TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_id),
                    UNIQUE(namespace, identity_digest)
                );

                CREATE TABLE IF NOT EXISTS operation_outbox (
                    namespace TEXT NOT NULL,
                    outbox_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    operation_version INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    PRIMARY KEY(namespace, outbox_id),
                    UNIQUE(namespace, operation_id, operation_version),
                    FOREIGN KEY(namespace, operation_id)
                        REFERENCES operation_state(namespace, operation_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_operation_outbox_pending
                ON operation_outbox(namespace, published_at, created_at);
                """
            )

    @staticmethod
    def _stored_from_row(row: sqlite3.Row) -> StoredOperation:
        try:
            envelope = OperationEnvelope(
                operation_id=row["operation_id"],
                tenant_id=row["tenant_id"],
                actor_id=row["actor_id"],
                capability=row["capability"],
                created_at=_parse_time(row["created_at"], "created_at"),
                deadline=_parse_time(row["deadline"], "deadline"),
                idempotency_key=row["idempotency_key"],
                trace_id=row["trace_id"],
                state=OperationState(row["state"]),
            )
            version = int(row["version"])
            if version < 1:
                raise ValueError("version must be positive")
            updated_at = _parse_time(row["updated_at"], "updated_at")
        except (
            KeyError,
            TypeError,
            ValueError,
            OperationContractError,
        ) as exc:
            if isinstance(exc, OperationStoreCorruptionError):
                raise
            raise OperationStoreCorruptionError(
                "persisted operation violates canonical contract"
            ) from exc

        if row["identity_digest"] != envelope.identity_digest:
            raise OperationStoreCorruptionError(
                "persisted operation identity digest mismatch"
            )
        return StoredOperation(
            envelope=envelope,
            version=version,
            updated_at=updated_at,
        )

    @staticmethod
    def _outbox_from_row(row: sqlite3.Row) -> OperationOutboxEvent:
        try:
            version = int(row["operation_version"])
            if version < 1:
                raise ValueError("operation_version must be positive")
            published_at = (
                None
                if row["published_at"] is None
                else _parse_time(row["published_at"], "published_at")
            )
            return OperationOutboxEvent(
                outbox_id=row["outbox_id"],
                operation_id=row["operation_id"],
                operation_version=version,
                event_type=row["event_type"],
                payload=_strict_json_object(row["payload_json"]),
                created_at=_parse_time(row["created_at"], "created_at"),
                published_at=published_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, OperationStoreCorruptionError):
                raise
            raise OperationStoreCorruptionError(
                "persisted operation outbox row is invalid"
            ) from exc

    def _select_operation(
        self,
        *,
        operation_id: str | None = None,
        identity_digest: str | None = None,
    ) -> sqlite3.Row | None:
        if operation_id is not None:
            return self._connection.execute(
                """
                SELECT *
                FROM operation_state
                WHERE namespace = ? AND operation_id = ?
                """,
                (self.namespace, operation_id),
            ).fetchone()
        if identity_digest is not None:
            return self._connection.execute(
                """
                SELECT *
                FROM operation_state
                WHERE namespace = ? AND identity_digest = ?
                """,
                (self.namespace, identity_digest),
            ).fetchone()
        raise ValueError("operation_id or identity_digest is required")

    def _insert_outbox(
        self,
        envelope: OperationEnvelope,
        *,
        version: int,
        created_at: datetime,
    ) -> None:
        event_type = f"operation.{OperationState(envelope.state).value}"
        outbox_id = _event_id(self.namespace, envelope.operation_id, version)
        payload = {
            "state": OperationState(envelope.state).value,
            "version": version,
            "trace_id": envelope.trace_id,
        }
        self._connection.execute(
            """
            INSERT INTO operation_outbox(
                namespace, outbox_id, operation_id, operation_version,
                event_type, payload_json, created_at, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                self.namespace,
                outbox_id,
                envelope.operation_id,
                version,
                event_type,
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                created_at.isoformat(),
            ),
        )

    def create(
        self,
        envelope: OperationEnvelope,
        *,
        now: datetime | None = None,
    ) -> StoredOperation:
        if not isinstance(envelope, OperationEnvelope):
            raise TypeError("envelope must be an OperationEnvelope")
        if OperationState(envelope.state) is not OperationState.CREATED:
            raise OperationStoreConflict("new operation must start in created state")
        instant = _aware(now or _utc_now(), "now")

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_operation(operation_id=envelope.operation_id)
                if row is not None:
                    existing = self._stored_from_row(row)
                    if existing.envelope.as_dict() != envelope.as_dict():
                        raise OperationStoreConflict(
                            "operation_id already exists with different content"
                        )
                    self._connection.execute("COMMIT")
                    return existing

                row = self._select_operation(
                    identity_digest=envelope.identity_digest
                )
                if row is not None:
                    existing = self._stored_from_row(row)
                    self._connection.execute("COMMIT")
                    return existing

                self._connection.execute(
                    """
                    INSERT INTO operation_state(
                        namespace, operation_id, identity_digest,
                        tenant_id, actor_id, capability,
                        created_at, deadline, idempotency_key, trace_id,
                        state, version, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        self.namespace,
                        envelope.operation_id,
                        envelope.identity_digest,
                        envelope.tenant_id,
                        envelope.actor_id,
                        envelope.capability,
                        envelope.created_at.astimezone(timezone.utc).isoformat(),
                        envelope.deadline.astimezone(timezone.utc).isoformat(),
                        envelope.idempotency_key,
                        envelope.trace_id,
                        OperationState(envelope.state).value,
                        instant.isoformat(),
                    ),
                )
                self._insert_outbox(envelope, version=1, created_at=instant)
                self._connection.execute("COMMIT")
                return StoredOperation(
                    envelope=envelope,
                    version=1,
                    updated_at=instant,
                )
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise OperationStoreConflict(
                    "operation durable identity conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(self, operation_id: str) -> StoredOperation:
        with self._lock:
            row = self._select_operation(operation_id=operation_id)
            if row is None:
                raise OperationStoreError("unknown operation")
            return self._stored_from_row(row)

    def get_by_identity_digest(self, identity_digest: str) -> StoredOperation:
        digest = str(identity_digest).strip()
        if not digest:
            raise OperationStoreError("identity_digest is required")
        with self._lock:
            row = self._select_operation(identity_digest=digest)
            if row is None:
                raise OperationStoreError("unknown operation identity")
            return self._stored_from_row(row)

    def transition(
        self,
        operation_id: str,
        target: OperationState | str,
        *,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> StoredOperation:
        if expected_version is not None and (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            raise ValueError("expected_version must be a positive integer")
        instant = _aware(now or _utc_now(), "now")

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_operation(operation_id=operation_id)
                if row is None:
                    raise OperationStoreError("unknown operation")
                current = self._stored_from_row(row)
                if (
                    expected_version is not None
                    and current.version != expected_version
                ):
                    raise OperationStoreConflict(
                        "operation version changed before transition"
                    )

                next_envelope = current.envelope.transition(target)
                next_version = current.version + 1
                cursor = self._connection.execute(
                    """
                    UPDATE operation_state
                    SET state = ?, version = ?, updated_at = ?
                    WHERE namespace = ? AND operation_id = ? AND version = ?
                    """,
                    (
                        OperationState(next_envelope.state).value,
                        next_version,
                        instant.isoformat(),
                        self.namespace,
                        operation_id,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise OperationStoreConflict(
                        "operation version changed during transition"
                    )
                self._insert_outbox(
                    next_envelope,
                    version=next_version,
                    created_at=instant,
                )
                self._connection.execute("COMMIT")
                return StoredOperation(
                    envelope=next_envelope,
                    version=next_version,
                    updated_at=instant,
                )
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise OperationStoreConflict(
                    "operation transition persistence conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def pending_outbox(
        self,
        *,
        operation_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[OperationOutboxEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        operation = None
        if operation_id is not None:
            operation = str(operation_id).strip()
            if not operation:
                raise OperationStoreError("operation_id is required")

        with self._lock:
            if operation is None:
                rows = self._connection.execute(
                    """
                    SELECT *
                    FROM operation_outbox
                    WHERE namespace = ? AND published_at IS NULL
                    ORDER BY created_at ASC, operation_id ASC, operation_version ASC
                    LIMIT ?
                    """,
                    (self.namespace, limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT *
                    FROM operation_outbox
                    WHERE namespace = ? AND operation_id = ? AND published_at IS NULL
                    ORDER BY operation_version ASC
                    LIMIT ?
                    """,
                    (self.namespace, operation, limit),
                ).fetchall()
        return tuple(self._outbox_from_row(row) for row in rows)

    def acknowledge_outbox(
        self,
        outbox_id: str,
        *,
        published_at: datetime | None = None,
    ) -> OperationOutboxEvent:
        event_id = str(outbox_id).strip()
        if not event_id:
            raise OperationStoreError("outbox_id is required")
        instant = _aware(published_at or _utc_now(), "published_at")

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT *
                    FROM operation_outbox
                    WHERE namespace = ? AND outbox_id = ?
                    """,
                    (self.namespace, event_id),
                ).fetchone()
                if row is None:
                    raise OperationStoreError("unknown operation outbox event")
                current = self._outbox_from_row(row)
                if current.published_at is not None:
                    self._connection.execute("COMMIT")
                    return current

                self._connection.execute(
                    """
                    UPDATE operation_outbox
                    SET published_at = ?
                    WHERE namespace = ? AND outbox_id = ?
                    """,
                    (instant.isoformat(), self.namespace, event_id),
                )
                self._connection.execute("COMMIT")
                return OperationOutboxEvent(
                    outbox_id=current.outbox_id,
                    operation_id=current.operation_id,
                    operation_version=current.operation_version,
                    event_type=current.event_type,
                    payload=dict(current.payload),
                    created_at=current.created_at,
                    published_at=instant,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteOperationStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "OperationOutboxEvent",
    "OperationStoreConflict",
    "OperationStoreCorruptionError",
    "OperationStoreError",
    "SQLiteOperationStore",
    "StoredOperation",
]
