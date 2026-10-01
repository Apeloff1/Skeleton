"""Projection seam from published outbox to inbox and tenant epoch fence.

This module does not own operation truth and does not sign work off.
DurableOperationRuntime remains the publisher. SpineProjection only consumes
already-published outbox identities, accepts them exactly once, and advances
a tenant fence when the accept is new.

A conflict is journaled as poison and does not move the fence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from typing import Any

from skeleton.persistence.consistency_fence import (
    ConsistencyConflict,
    ConsistencyFenceError,
    SQLiteConsistencyFence,
)
from skeleton.persistence.inbox_ledger import (
    InboxConflict,
    SQLiteInboxLedger,
    delivery_from_outbox,
)
from skeleton.persistence.operation_store import (
    OperationOutboxEvent,
    SQLiteOperationStore,
)


class SpineProjectionError(RuntimeError):
    """Base projection failure. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class PoisonMark:
    outbox_id: str
    operation_id: str
    tenant_id: str
    reason: str
    recorded_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "outbox_id": self.outbox_id,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "reason": self.reason,
            "recorded_at": self.recorded_at.isoformat(),
            "stored_prose": 0,
            "completion_checkbox": False,
        }


@dataclass(frozen=True, slots=True)
class SpineProjectionReport:
    scanned: int
    applied: int
    duplicates: int
    poisoned: int
    fence_advances: int
    reconciled: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "spine_projection",
            "hit": self.poisoned == 0,
            "law": "published-outbox-to-inbox-fence",
            "citation": "VOL-134",
            "scanned": self.scanned,
            "applied": self.applied,
            "duplicates": self.duplicates,
            "poisoned": self.poisoned,
            "fence_advances": self.fence_advances,
            "reconciled": self.reconciled,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


def _resource(operation_id: str) -> str:
    return f"op:{operation_id}"


def _reason_code(exc: BaseException) -> str:
    text = type(exc).__name__
    if len(text) > 64:
        text = text[:64]
    return text


class SpineProjection:
    """Consume published outbox rows into one inbox consumer and one fence."""

    def __init__(
        self,
        operations: SQLiteOperationStore,
        inbox: SQLiteInboxLedger,
        fence: SQLiteConsistencyFence,
        *,
        consumer_id: str = "spine-projection",
        journal_path: str | Path = ":memory:",
    ) -> None:
        if not isinstance(operations, SQLiteOperationStore):
            raise TypeError("operations must be a SQLiteOperationStore")
        if not isinstance(inbox, SQLiteInboxLedger):
            raise TypeError("inbox must be a SQLiteInboxLedger")
        if not isinstance(fence, SQLiteConsistencyFence):
            raise TypeError("fence must be a SQLiteConsistencyFence")
        self.operations = operations
        self.inbox = inbox
        self.fence = fence
        self.consumer_id = consumer_id
        self._connection = sqlite3.connect(
            str(journal_path),
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
                CREATE TABLE IF NOT EXISTS projection_poison (
                    outbox_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projection_cursor (
                    consumer_id TEXT PRIMARY KEY,
                    applied_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projection_applied (
                    outbox_id TEXT PRIMARY KEY,
                    consumer_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    fence_epoch INTEGER NOT NULL,
                    completed_at TEXT NOT NULL
                );
                """
            )

    def project(self, *, limit: int = 1000, now: datetime | None = None) -> SpineProjectionReport:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise SpineProjectionError("limit must be a positive integer")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise SpineProjectionError("now must be timezone-aware")
        events = self.operations.published_outbox(limit=limit)
        applied = 0
        duplicates = 0
        poisoned = 0
        advances = 0
        reconciled = 0
        for event in events:
            outcome = self._project_one(event, instant)
            applied += outcome[0]
            duplicates += outcome[1]
            poisoned += outcome[2]
            advances += outcome[3]
            reconciled += outcome[4]
        return SpineProjectionReport(
            scanned=len(events),
            applied=applied,
            duplicates=duplicates,
            poisoned=poisoned,
            fence_advances=advances,
            reconciled=reconciled,
        )

    def _project_one(
        self,
        event: OperationOutboxEvent,
        instant: datetime,
    ) -> tuple[int, int, int, int, int]:
        stored = self.operations.get(event.operation_id)
        tenant_id = stored.envelope.tenant_id
        try:
            delivery = delivery_from_outbox(event, tenant_id)
            result = self.inbox.accept(
                delivery,
                consumer_id=self.consumer_id,
                now=event.published_at or instant,
            )
        except InboxConflict as exc:
            self._poison(event, tenant_id, _reason_code(exc), instant)
            return (0, 0, 1, 0, 0)
        resource = _resource(event.operation_id)
        try:
            advanced = self._reconcile_fence(
                tenant_id=tenant_id,
                resource_id=resource,
                target_epoch=result.applied_through,
                now=event.published_at or instant,
            )
        except ConsistencyFenceError as exc:
            self._poison(event, tenant_id, _reason_code(exc), instant)
            return (0, 0, 1, 0, 0)
        try:
            completed = self._record_completion(
                event=event,
                tenant_id=tenant_id,
                fence_epoch=result.applied_through,
                instant=instant,
            )
        except SpineProjectionError as exc:
            self._poison(event, tenant_id, _reason_code(exc), instant)
            return (0, 0, 1, advanced, 0)
        if result.duplicate:
            return (0, 1, 0, advanced, completed)
        if completed != 1:
            self._poison(
                event,
                tenant_id,
                "CompletionAlreadyExists",
                instant,
            )
            return (0, 0, 1, advanced, 0)
        return (1, 0, 0, advanced, 0)

    def _reconcile_fence(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        target_epoch: int,
        now: datetime,
    ) -> int:
        if (
            isinstance(target_epoch, bool)
            or not isinstance(target_epoch, int)
            or target_epoch < 1
        ):
            raise ConsistencyConflict(
                "inbox watermark must be a positive fence target"
            )
        try:
            current = self.fence.read(
                tenant_id=tenant_id,
                resource_id=resource_id,
            )
        except ConsistencyFenceError as exc:
            if str(exc) != "unknown fence":
                raise
            if target_epoch != 1:
                raise ConsistencyConflict(
                    "fence is missing behind inbox watermark"
                ) from exc
            expected = 0
        else:
            if current.epoch == target_epoch:
                return 0
            if current.epoch != target_epoch - 1:
                raise ConsistencyConflict(
                    "fence epoch does not trail inbox watermark by one"
                )
            expected = current.epoch

        try:
            token = self.fence.compare_and_advance(
                tenant_id=tenant_id,
                resource_id=resource_id,
                expected_epoch=expected,
                writer_id=self.consumer_id,
                now=now,
            )
        except ConsistencyConflict:
            current = self.fence.read(
                tenant_id=tenant_id,
                resource_id=resource_id,
            )
            if current.epoch == target_epoch:
                return 0
            raise
        if token.epoch != target_epoch:
            raise ConsistencyConflict(
                "fence advance did not reach inbox watermark"
            )
        return 1

    def _poison(
        self,
        event: OperationOutboxEvent,
        tenant_id: str,
        reason: str,
        instant: datetime,
    ) -> None:
        digest = hashlib.sha256(
            json.dumps(
                {"outbox_id": event.outbox_id, "reason": reason},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO projection_poison(
                    outbox_id, operation_id, tenant_id, reason, digest, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(outbox_id) DO NOTHING
                """,
                (
                    event.outbox_id,
                    event.operation_id,
                    tenant_id,
                    reason,
                    digest,
                    instant.isoformat(),
                ),
            )

    def _record_completion(
        self,
        *,
        event: OperationOutboxEvent,
        tenant_id: str,
        fence_epoch: int,
        instant: datetime,
    ) -> int:
        if (
            isinstance(fence_epoch, bool)
            or not isinstance(fence_epoch, int)
            or fence_epoch < 1
        ):
            raise SpineProjectionError(
                "fence_epoch must be a positive integer"
            )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    """
                    SELECT consumer_id, operation_id, tenant_id, fence_epoch
                    FROM projection_applied
                    WHERE outbox_id = ?
                    """,
                    (event.outbox_id,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["consumer_id"] != self.consumer_id
                        or existing["operation_id"] != event.operation_id
                        or existing["tenant_id"] != tenant_id
                        or existing["fence_epoch"] != fence_epoch
                    ):
                        raise SpineProjectionError(
                            "projection completion identity changed"
                        )
                    self._connection.execute("COMMIT")
                    return 0
                self._connection.execute(
                    """
                    INSERT INTO projection_applied(
                        outbox_id, consumer_id, operation_id, tenant_id,
                        fence_epoch, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.outbox_id,
                        self.consumer_id,
                        event.operation_id,
                        tenant_id,
                        fence_epoch,
                        instant.isoformat(),
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO projection_cursor(
                        consumer_id, applied_count, updated_at
                    )
                    VALUES (?, 1, ?)
                    ON CONFLICT(consumer_id) DO UPDATE SET
                        applied_count = projection_cursor.applied_count + 1,
                        updated_at = excluded.updated_at
                    """,
                    (self.consumer_id, instant.isoformat()),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return 1

    def poison_count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM projection_poison"
            ).fetchone()
        return int(row["n"])

    def card(self) -> dict[str, Any]:
        return {
            "kind": "spine_projection",
            "hit": True,
            "law": "published-outbox-to-inbox-fence",
            "citation": "VOL-134",
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
            "poison_count": self.poison_count(),
        }

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SpineProjection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
