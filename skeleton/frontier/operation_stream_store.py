"""Durable SQLite storage for the canonical operation stream protocol.

The transport protocol lives in skeleton.frontier.operation_stream. This module
implements persistence only. It preserves the protocol's monotonic sequence,
event identity, terminal finality, replay-gap, and explicit compaction rules.

SQLite is the portable reference durable backend. Production deployments may
substitute another store only if the same conformance tests pass.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
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
    "StreamStoreCorruptionError",
]
