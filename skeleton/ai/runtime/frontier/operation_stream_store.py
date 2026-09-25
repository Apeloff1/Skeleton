"""Durable SQLite storage for the canonical operation stream protocol.

The transport protocol lives in skeleton.frontier.operation_stream. This module
implements persistence only. It preserves the protocol's monotonic sequence,
event identity, terminal finality, replay-gap, and explicit compaction rules.

SQLite is the portable reference durable backend. Production deployments may
substitute another store only if the same conformance tests pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any
from uuid import uuid4

from skeleton.frontier.operation_stream import (
    OperationEventLog,
    ReplayCursor,
    StreamBackpressureError,
    StreamContractError,
    StreamDuplicateConflictError,
    StreamEvent,
    StreamReplayGapError,
    StreamTerminalError,
)


class StreamStoreCorruptionError(StreamContractError):
    """Persisted stream state cannot be interpreted safely."""


_CONSUMER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _consumer_id(value: str) -> str:
    if not isinstance(value, str):
        raise StreamContractError("consumer_id must be a string")
    normalized = value.strip()
    if not _CONSUMER_ID_RE.fullmatch(normalized):
        raise StreamContractError(
            "consumer_id must be 1-128 characters using A-Z a-z 0-9 . _ : -"
        )
    return normalized


_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _worker_id(value: str) -> str:
    if not isinstance(value, str):
        raise StreamContractError("worker_id must be a string")
    normalized = value.strip()
    if not _WORKER_ID_RE.fullmatch(normalized):
        raise StreamContractError(
            "worker_id must be 1-128 characters using A-Z a-z 0-9 . _ : -"
        )
    return normalized


def _aware_utc(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if not isinstance(instant, datetime):
        raise StreamContractError("consumer timestamp must be a datetime")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise StreamContractError("consumer timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class StreamConsumerCheckpoint:
    operation_id: str
    consumer_id: str
    acknowledged_through: int
    lease_expires_at: datetime
    updated_at: datetime

    @property
    def active(self) -> bool:
        return self.lease_expires_at > datetime.now(timezone.utc)

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "consumer_id": self.consumer_id,
            "acknowledged_through": self.acknowledged_through,
            "lease_expires_at": self.lease_expires_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class StreamWorkerLease:
    operation_id: str
    worker_id: str
    generation: int
    lease_expires_at: datetime
    updated_at: datetime

    @property
    def active(self) -> bool:
        return self.lease_expires_at > datetime.now(timezone.utc)

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "lease_expires_at": self.lease_expires_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class SQLiteOperationEventStore:
    """Transactional durable store for operation events and replay watermarks."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "operation_stream",
        capacity_per_operation: int = 100_000,
    ) -> None:
        namespace = namespace.strip()
        if not namespace:
            raise ValueError("namespace must not be empty")
        if (
            isinstance(capacity_per_operation, bool)
            or not isinstance(capacity_per_operation, int)
            or capacity_per_operation < 1
        ):
            raise ValueError("capacity_per_operation must be a positive integer")

        self.namespace = namespace
        self.capacity_per_operation = capacity_per_operation
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
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS operation_stream_head (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    compacted_through INTEGER NOT NULL DEFAULT 0,
                    terminal INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(namespace, operation_id)
                );

                CREATE TABLE IF NOT EXISTS operation_stream_event (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_id, sequence),
                    UNIQUE(namespace, operation_id, event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_operation_stream_replay
                ON operation_stream_event(namespace, operation_id, sequence);

                CREATE TABLE IF NOT EXISTS operation_stream_consumer (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    consumer_id TEXT NOT NULL,
                    acknowledged_through INTEGER NOT NULL DEFAULT 0,
                    lease_expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_id, consumer_id)
                );

                CREATE INDEX IF NOT EXISTS idx_operation_stream_consumer_lease
                ON operation_stream_consumer(
                    namespace, operation_id, lease_expires_at
                );

                CREATE TABLE IF NOT EXISTS operation_stream_worker_lease (
                    namespace TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, operation_id)
                );

                CREATE INDEX IF NOT EXISTS idx_operation_stream_worker_lease_expiry
                ON operation_stream_worker_lease(namespace, lease_expires_at);
                """
            )

    @staticmethod
    def _encode_payload(event: StreamEvent) -> str:
        try:
            return json.dumps(
                dict(event.payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise StreamContractError("stream payload must be strict JSON") from exc

    @staticmethod
    def _decode_payload(raw: object) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise StreamStoreCorruptionError("payload_json must be text")
        try:
            value = json.loads(
                raw,
                parse_constant=_reject_constant,
                object_pairs_hook=_unique_object,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise StreamStoreCorruptionError("persisted stream payload is invalid") from exc
        if not isinstance(value, dict):
            raise StreamStoreCorruptionError("persisted stream payload must be an object")
        return value

    @staticmethod
    def _decode_timestamp(raw: object) -> datetime:
        if not isinstance(raw, str):
            raise StreamStoreCorruptionError("timestamp must be text")
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise StreamStoreCorruptionError("timestamp must be ISO-8601") from exc
        if value.tzinfo is None or value.utcoffset() is None:
            raise StreamStoreCorruptionError("timestamp must be timezone-aware")
        return value

    @classmethod
    def _event_from_row(cls, row: sqlite3.Row) -> StreamEvent:
        try:
            return StreamEvent(
                operation_id=row["operation_id"],
                event_id=row["event_id"],
                sequence=int(row["sequence"]),
                type=row["event_type"],
                timestamp=cls._decode_timestamp(row["timestamp"]),
                payload=cls._decode_payload(row["payload_json"]),
            )
        except (KeyError, TypeError, ValueError, StreamContractError) as exc:
            if isinstance(exc, StreamStoreCorruptionError):
                raise
            raise StreamStoreCorruptionError(
                "persisted operation event violates canonical contract"
            ) from exc

    def _ensure_head(self, operation_id: str) -> sqlite3.Row:
        # Reuse protocol validation without inventing another operation-id parser.
        OperationEventLog(operation_id, capacity=1)
        self._connection.execute(
            """
            INSERT OR IGNORE INTO operation_stream_head(
                namespace, operation_id, compacted_through, terminal
            ) VALUES (?, ?, 0, 0)
            """,
            (self.namespace, operation_id),
        )
        row = self._connection.execute(
            """
            SELECT compacted_through, terminal
            FROM operation_stream_head
            WHERE namespace = ? AND operation_id = ?
            """,
            (self.namespace, operation_id),
        ).fetchone()
        if row is None:
            raise StreamStoreCorruptionError("operation stream head disappeared")
        return row

    def append_event(self, event: StreamEvent) -> StreamEvent:
        """Append exactly the next event or return an identical duplicate."""

        payload_json = self._encode_payload(event)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                head = self._ensure_head(event.operation_id)
                duplicate = self._connection.execute(
                    """
                    SELECT operation_id, sequence, event_id, event_type, timestamp, payload_json
                    FROM operation_stream_event
                    WHERE namespace = ? AND operation_id = ? AND event_id = ?
                    """,
                    (self.namespace, event.operation_id, event.event_id),
                ).fetchone()
                if duplicate is not None:
                    prior = self._event_from_row(duplicate)
                    if prior.as_dict() == event.as_dict():
                        self._connection.execute("COMMIT")
                        return prior
                    raise StreamDuplicateConflictError(
                        "event_id already exists with different event content"
                    )

                if int(head["terminal"]):
                    raise StreamTerminalError("operation stream is already terminal")

                count_row = self._connection.execute(
                    """
                    SELECT COUNT(*), COALESCE(MAX(sequence), 0)
                    FROM operation_stream_event
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (self.namespace, event.operation_id),
                ).fetchone()
                retained = int(count_row[0])
                latest = int(count_row[1])
                compacted = int(head["compacted_through"])
                if retained >= self.capacity_per_operation:
                    raise StreamBackpressureError(
                        "durable operation stream capacity reached"
                    )
                expected = max(latest, compacted) + 1
                if event.sequence != expected:
                    raise StreamContractError(
                        f"out-of-order durable sequence: expected {expected}, got {event.sequence}"
                    )

                self._connection.execute(
                    """
                    INSERT INTO operation_stream_event(
                        namespace, operation_id, sequence, event_id,
                        event_type, timestamp, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        event.operation_id,
                        event.sequence,
                        event.event_id,
                        event.type,
                        event.timestamp.isoformat(),
                        payload_json,
                    ),
                )
                if event.terminal:
                    self._connection.execute(
                        """
                        UPDATE operation_stream_head
                        SET terminal = 1
                        WHERE namespace = ? AND operation_id = ?
                        """,
                        (self.namespace, event.operation_id),
                    )
                self._connection.execute("COMMIT")
                return event
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def append(
        self,
        operation_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> StreamEvent:
        """Mint and append the next event transactionally."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                head = self._ensure_head(operation_id)
                if event_id is not None:
                    duplicate = self._connection.execute(
                        """
                        SELECT operation_id, sequence, event_id, event_type, timestamp, payload_json
                        FROM operation_stream_event
                        WHERE namespace = ? AND operation_id = ? AND event_id = ?
                        """,
                        (self.namespace, operation_id, event_id),
                    ).fetchone()
                    if duplicate is not None:
                        prior = self._event_from_row(duplicate)
                        candidate_payload = dict(payload)
                        if (
                            prior.type == event_type
                            and prior.timestamp == (timestamp or prior.timestamp)
                            and dict(prior.payload) == candidate_payload
                        ):
                            self._connection.execute("COMMIT")
                            return prior
                        raise StreamDuplicateConflictError(
                            "event_id already exists with different event content"
                        )

                if int(head["terminal"]):
                    raise StreamTerminalError("operation stream is already terminal")
                count_row = self._connection.execute(
                    """
                    SELECT COUNT(*), COALESCE(MAX(sequence), 0)
                    FROM operation_stream_event
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (self.namespace, operation_id),
                ).fetchone()
                retained = int(count_row[0])
                latest = int(count_row[1])
                compacted = int(head["compacted_through"])
                if retained >= self.capacity_per_operation:
                    raise StreamBackpressureError(
                        "durable operation stream capacity reached"
                    )
                event = StreamEvent(
                    operation_id=operation_id,
                    event_id=event_id or str(uuid4()),
                    sequence=max(latest, compacted) + 1,
                    type=event_type,
                    timestamp=timestamp or datetime.now().astimezone(),
                    payload=payload,
                )
                payload_json = self._encode_payload(event)
                self._connection.execute(
                    """
                    INSERT INTO operation_stream_event(
                        namespace, operation_id, sequence, event_id,
                        event_type, timestamp, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        operation_id,
                        event.sequence,
                        event.event_id,
                        event.type,
                        event.timestamp.isoformat(),
                        payload_json,
                    ),
                )
                if event.terminal:
                    self._connection.execute(
                        """
                        UPDATE operation_stream_head
                        SET terminal = 1
                        WHERE namespace = ? AND operation_id = ?
                        """,
                        (self.namespace, operation_id),
                    )
                self._connection.execute("COMMIT")
                return event
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise StreamDuplicateConflictError(
                    "durable stream identity conflict"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def replay(
        self,
        cursor: ReplayCursor,
        *,
        limit: int = 1000,
    ) -> tuple[StreamEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            head = self._ensure_head(cursor.operation_id)
            compacted = int(head["compacted_through"])
            if cursor.after_sequence < compacted:
                raise StreamReplayGapError(
                    "requested replay cursor predates durable retained history"
                )
            rows = self._connection.execute(
                """
                SELECT operation_id, sequence, event_id, event_type, timestamp, payload_json
                FROM operation_stream_event
                WHERE namespace = ? AND operation_id = ? AND sequence > ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (
                    self.namespace,
                    cursor.operation_id,
                    cursor.after_sequence,
                    limit,
                ),
            ).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    @classmethod
    def _consumer_from_row(
        cls,
        row: sqlite3.Row,
    ) -> StreamConsumerCheckpoint:
        try:
            acknowledged = int(row["acknowledged_through"])
            if acknowledged < 0:
                raise ValueError("acknowledged_through must be non-negative")
            return StreamConsumerCheckpoint(
                operation_id=row["operation_id"],
                consumer_id=_consumer_id(row["consumer_id"]),
                acknowledged_through=acknowledged,
                lease_expires_at=cls._decode_timestamp(row["lease_expires_at"]),
                updated_at=cls._decode_timestamp(row["updated_at"]),
            )
        except (KeyError, TypeError, ValueError, StreamContractError) as exc:
            if isinstance(exc, StreamStoreCorruptionError):
                raise
            raise StreamStoreCorruptionError(
                "persisted stream consumer checkpoint is invalid"
            ) from exc

    def register_consumer(
        self,
        operation_id: str,
        consumer_id: str,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> StreamConsumerCheckpoint:
        consumer = _consumer_id(consumer_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 1
            or lease_seconds > 86_400
        ):
            raise ValueError("lease_seconds must be an integer between 1 and 86400")
        instant = _aware_utc(now)
        expires = instant + timedelta(seconds=lease_seconds)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_head(operation_id)
                row = self._connection.execute(
                    """
                    SELECT operation_id, consumer_id, acknowledged_through,
                           lease_expires_at, updated_at
                    FROM operation_stream_consumer
                    WHERE namespace = ? AND operation_id = ? AND consumer_id = ?
                    """,
                    (self.namespace, operation_id, consumer),
                ).fetchone()
                acknowledged = 0 if row is None else int(row["acknowledged_through"])
                self._connection.execute(
                    """
                    INSERT INTO operation_stream_consumer(
                        namespace, operation_id, consumer_id,
                        acknowledged_through, lease_expires_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, operation_id, consumer_id)
                    DO UPDATE SET
                        lease_expires_at = excluded.lease_expires_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self.namespace,
                        operation_id,
                        consumer,
                        acknowledged,
                        expires.isoformat(),
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return StreamConsumerCheckpoint(
                    operation_id=operation_id,
                    consumer_id=consumer,
                    acknowledged_through=acknowledged,
                    lease_expires_at=expires,
                    updated_at=instant,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def acknowledge_consumer(
        self,
        operation_id: str,
        consumer_id: str,
        sequence: int,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> StreamConsumerCheckpoint:
        consumer = _consumer_id(consumer_id)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 1
            or lease_seconds > 86_400
        ):
            raise ValueError("lease_seconds must be an integer between 1 and 86400")
        instant = _aware_utc(now)
        expires = instant + timedelta(seconds=lease_seconds)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                head = self._ensure_head(operation_id)
                latest_row = self._connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), ?)
                    FROM operation_stream_event
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (
                        int(head["compacted_through"]),
                        self.namespace,
                        operation_id,
                    ),
                ).fetchone()
                latest = int(latest_row[0])
                if sequence > latest:
                    raise StreamContractError(
                        "cannot acknowledge beyond latest durable sequence"
                    )

                row = self._connection.execute(
                    """
                    SELECT operation_id, consumer_id, acknowledged_through,
                           lease_expires_at, updated_at
                    FROM operation_stream_consumer
                    WHERE namespace = ? AND operation_id = ? AND consumer_id = ?
                    """,
                    (self.namespace, operation_id, consumer),
                ).fetchone()
                if row is None:
                    raise StreamContractError(
                        "consumer must register before acknowledging"
                    )
                current = int(row["acknowledged_through"])
                acknowledged = max(current, sequence)
                self._connection.execute(
                    """
                    UPDATE operation_stream_consumer
                    SET acknowledged_through = ?,
                        lease_expires_at = ?,
                        updated_at = ?
                    WHERE namespace = ? AND operation_id = ? AND consumer_id = ?
                    """,
                    (
                        acknowledged,
                        expires.isoformat(),
                        instant.isoformat(),
                        self.namespace,
                        operation_id,
                        consumer,
                    ),
                )
                self._connection.execute("COMMIT")
                return StreamConsumerCheckpoint(
                    operation_id=operation_id,
                    consumer_id=consumer,
                    acknowledged_through=acknowledged,
                    lease_expires_at=expires,
                    updated_at=instant,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    @classmethod
    def _worker_lease_from_row(cls, row: sqlite3.Row) -> StreamWorkerLease:
        try:
            generation = int(row["generation"])
            if generation < 1:
                raise ValueError("generation must be positive")
            return StreamWorkerLease(
                operation_id=row["operation_id"],
                worker_id=_worker_id(row["worker_id"]),
                generation=generation,
                lease_expires_at=cls._decode_timestamp(row["lease_expires_at"]),
                updated_at=cls._decode_timestamp(row["updated_at"]),
            )
        except (KeyError, TypeError, ValueError, StreamContractError) as exc:
            if isinstance(exc, StreamStoreCorruptionError):
                raise
            raise StreamStoreCorruptionError("persisted stream worker lease is invalid") from exc

    def acquire_worker_lease(
        self,
        operation_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 10,
        now: datetime | None = None,
    ) -> StreamWorkerLease | None:
        """Acquire a fenced per-operation projection lease."""
        worker = _worker_id(worker_id)
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be an integer between 1 and 300")
        instant = _aware_utc(now)
        expires = instant + timedelta(seconds=lease_seconds)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_head(operation_id)
                row = self._connection.execute(
                    """
                    SELECT operation_id, worker_id, generation, lease_expires_at, updated_at
                    FROM operation_stream_worker_lease
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (self.namespace, operation_id),
                ).fetchone()
                generation = 1
                if row is not None:
                    current = self._worker_lease_from_row(row)
                    if current.lease_expires_at > instant:
                        self._connection.execute("COMMIT")
                        return None
                    generation = current.generation + 1
                self._connection.execute(
                    """
                    INSERT INTO operation_stream_worker_lease(
                        namespace, operation_id, worker_id, generation, lease_expires_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, operation_id)
                    DO UPDATE SET worker_id = excluded.worker_id,
                                  generation = excluded.generation,
                                  lease_expires_at = excluded.lease_expires_at,
                                  updated_at = excluded.updated_at
                    """,
                    (self.namespace, operation_id, worker, generation, expires.isoformat(), instant.isoformat()),
                )
                self._connection.execute("COMMIT")
                return StreamWorkerLease(operation_id, worker, generation, expires, instant)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def renew_worker_lease(
        self,
        operation_id: str,
        worker_id: str,
        generation: int,
        *,
        lease_seconds: int = 10,
        now: datetime | None = None,
    ) -> StreamWorkerLease | None:
        """Extend only the exact live lease generation held by this worker."""
        worker = _worker_id(worker_id)
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("generation must be a positive integer")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be an integer between 1 and 300")
        instant = _aware_utc(now)
        expires = instant + timedelta(seconds=lease_seconds)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT operation_id, worker_id, generation, lease_expires_at, updated_at
                    FROM operation_stream_worker_lease
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (self.namespace, operation_id),
                ).fetchone()
                if row is None:
                    self._connection.execute("COMMIT")
                    return None
                current = self._worker_lease_from_row(row)
                if current.worker_id != worker or current.generation != generation or current.lease_expires_at <= instant:
                    self._connection.execute("COMMIT")
                    return None
                self._connection.execute(
                    """
                    UPDATE operation_stream_worker_lease
                    SET lease_expires_at = ?, updated_at = ?
                    WHERE namespace = ? AND operation_id = ? AND worker_id = ? AND generation = ?
                    """,
                    (expires.isoformat(), instant.isoformat(), self.namespace, operation_id, worker, generation),
                )
                self._connection.execute("COMMIT")
                return StreamWorkerLease(operation_id, worker, generation, expires, instant)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def active_worker_lease(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> StreamWorkerLease | None:
        instant = _aware_utc(now)
        with self._lock:
            self._ensure_head(operation_id)
            row = self._connection.execute(
                """
                SELECT operation_id, worker_id, generation, lease_expires_at, updated_at
                FROM operation_stream_worker_lease
                WHERE namespace = ? AND operation_id = ? AND lease_expires_at > ?
                """,
                (self.namespace, operation_id, instant.isoformat()),
            ).fetchone()
        return None if row is None else self._worker_lease_from_row(row)

    def release_worker_lease(self, operation_id: str, worker_id: str, generation: int) -> bool:
        """Release only the matching fenced generation; stale releases are inert."""
        worker = _worker_id(worker_id)
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValueError("generation must be a positive integer")
        with self._lock:
            cursor = self._connection.execute(
                """
                DELETE FROM operation_stream_worker_lease
                WHERE namespace = ? AND operation_id = ? AND worker_id = ? AND generation = ?
                """,
                (self.namespace, operation_id, worker, generation),
            )
            return int(cursor.rowcount) == 1

    def active_consumers(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[StreamConsumerCheckpoint, ...]:
        instant = _aware_utc(now)
        with self._lock:
            self._ensure_head(operation_id)
            rows = self._connection.execute(
                """
                SELECT operation_id, consumer_id, acknowledged_through,
                       lease_expires_at, updated_at
                FROM operation_stream_consumer
                WHERE namespace = ? AND operation_id = ? AND lease_expires_at > ?
                ORDER BY acknowledged_through ASC, consumer_id ASC
                """,
                (self.namespace, operation_id, instant.isoformat()),
            ).fetchall()
        return tuple(self._consumer_from_row(row) for row in rows)

    def safe_compaction_sequence(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        """Return the slowest active consumer ACK, or current watermark if none."""

        instant = _aware_utc(now)
        with self._lock:
            head = self._ensure_head(operation_id)
            row = self._connection.execute(
                """
                SELECT MIN(acknowledged_through)
                FROM operation_stream_consumer
                WHERE namespace = ? AND operation_id = ? AND lease_expires_at > ?
                """,
                (self.namespace, operation_id, instant.isoformat()),
            ).fetchone()
            if row is None or row[0] is None:
                return int(head["compacted_through"])
            return max(int(head["compacted_through"]), int(row[0]))

    def compact_acknowledged(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        safe = self.safe_compaction_sequence(operation_id, now=now)
        return self.compact_through(operation_id, safe)

    def compact_through(self, operation_id: str, sequence: int) -> int:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                head = self._ensure_head(operation_id)
                current = int(head["compacted_through"])
                latest_row = self._connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), ?)
                    FROM operation_stream_event
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (current, self.namespace, operation_id),
                ).fetchone()
                latest = int(latest_row[0])
                if sequence > latest:
                    raise StreamContractError(
                        "cannot compact beyond latest durable sequence"
                    )
                if sequence <= current:
                    self._connection.execute("COMMIT")
                    return 0
                cursor = self._connection.execute(
                    """
                    DELETE FROM operation_stream_event
                    WHERE namespace = ? AND operation_id = ? AND sequence <= ?
                    """,
                    (self.namespace, operation_id, sequence),
                )
                self._connection.execute(
                    """
                    UPDATE operation_stream_head
                    SET compacted_through = ?
                    WHERE namespace = ? AND operation_id = ?
                    """,
                    (sequence, self.namespace, operation_id),
                )
                self._connection.execute("COMMIT")
                return int(cursor.rowcount)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def head(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            head = self._ensure_head(operation_id)
            latest_row = self._connection.execute(
                """
                SELECT COALESCE(MAX(sequence), ?)
                FROM operation_stream_event
                WHERE namespace = ? AND operation_id = ?
                """,
                (
                    int(head["compacted_through"]),
                    self.namespace,
                    operation_id,
                ),
            ).fetchone()
            return {
                "operation_id": operation_id,
                "compacted_through": int(head["compacted_through"]),
                "latest_sequence": int(latest_row[0]),
                "terminal": bool(head["terminal"]),
            }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteOperationEventStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "SQLiteOperationEventStore",
    "StreamConsumerCheckpoint",
    "StreamWorkerLease",
    "StreamStoreCorruptionError",
]
