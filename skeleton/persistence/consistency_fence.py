"""Tenant-scoped compare-and-advance fence for P2 consistency.

VOL-132 fence, not a consensus protocol and not a sign-off. A resource is
opened at epoch 1 for one tenant. Later writes must present the current
epoch and receive epoch + 1. Another tenant cannot observe or advance the
fence: missing and foreign-tenant reads both surface as unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from typing import Any


class ConsistencyFenceError(RuntimeError):
    """Base consistency-fence failure."""


class ConsistencyConflict(ConsistencyFenceError):
    """Epoch, writer, or tenant fence rejected the write."""


class ConsistencyCorruptionError(ConsistencyFenceError):
    """Persisted fence state cannot be interpreted safely."""


def _canonical_text(value: object, field: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConsistencyFenceError(f"{field} must be non-empty text")
    if value != value.strip():
        raise ConsistencyFenceError(f"{field} must be canonical text")
    if len(value) > max_length:
        raise ConsistencyFenceError(f"{field} exceeds maximum length")
    return value


def _epoch(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConsistencyFenceError(f"{field} must be an integer >= {minimum}")
    return value


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ConsistencyFenceError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConsistencyFenceError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ConsistencyCorruptionError(f"{field} must be persisted as text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConsistencyCorruptionError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConsistencyCorruptionError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class FenceToken:
    tenant_id: str
    resource_id: str
    epoch: int
    writer_id: str
    updated_at: datetime

    @property
    def digest(self) -> str:
        raw = f"{self.tenant_id}|{self.resource_id}|{self.epoch}|{self.writer_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "epoch": self.epoch,
            "writer_id": self.writer_id,
            "updated_at": self.updated_at.isoformat(),
            "digest": self.digest,
            "stored_prose": 0,
            "completion_checkbox": False,
        }


class SQLiteConsistencyFence:
    """SQLite epoch fence. Isolation is by tenant key, not by filter-after-read."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "consistency_fence",
    ) -> None:
        self.namespace = _canonical_text(namespace, "namespace")
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
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS consistency_fence (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    writer_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, resource_id)
                );
                """
            )

    def open(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        writer_id: str,
        now: datetime | None = None,
    ) -> FenceToken:
        return self.compare_and_advance(
            tenant_id=tenant_id,
            resource_id=resource_id,
            expected_epoch=0,
            writer_id=writer_id,
            now=now,
        )

    def compare_and_advance(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        expected_epoch: int,
        writer_id: str,
        now: datetime | None = None,
    ) -> FenceToken:
        tenant = _canonical_text(tenant_id, "tenant_id")
        resource = _canonical_text(resource_id, "resource_id")
        writer = _canonical_text(writer_id, "writer_id")
        expected = _epoch(expected_epoch, "expected_epoch", minimum=0)
        instant = _aware(now or datetime.now(timezone.utc), "now")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT epoch, writer_id, updated_at
                    FROM consistency_fence
                    WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                    """,
                    (self.namespace, tenant, resource),
                ).fetchone()
                if row is None:
                    if expected != 0:
                        raise ConsistencyConflict("unknown fence")
                    epoch = 1
                    self._connection.execute(
                        """
                        INSERT INTO consistency_fence(
                            namespace, tenant_id, resource_id, epoch, writer_id, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (self.namespace, tenant, resource, epoch, writer, instant.isoformat()),
                    )
                else:
                    current = row["epoch"]
                    if isinstance(current, bool) or not isinstance(current, int) or current < 1:
                        raise ConsistencyCorruptionError("epoch must be persisted >= 1")
                    if current != expected:
                        raise ConsistencyConflict("stale fence epoch")
                    updated = _parse_time(row["updated_at"], "updated_at")
                    if instant < updated:
                        raise ConsistencyConflict("fence advance cannot predate current token")
                    epoch = current + 1
                    self._connection.execute(
                        """
                        UPDATE consistency_fence
                        SET epoch = ?, writer_id = ?, updated_at = ?
                        WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                        """,
                        (
                            epoch,
                            writer,
                            instant.isoformat(),
                            self.namespace,
                            tenant,
                            resource,
                        ),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return FenceToken(
            tenant_id=tenant,
            resource_id=resource,
            epoch=epoch,
            writer_id=writer,
            updated_at=instant,
        )

    def read(self, *, tenant_id: str, resource_id: str) -> FenceToken:
        tenant = _canonical_text(tenant_id, "tenant_id")
        resource = _canonical_text(resource_id, "resource_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT epoch, writer_id, updated_at
                FROM consistency_fence
                WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                """,
                (self.namespace, tenant, resource),
            ).fetchone()
        if row is None:
            raise ConsistencyFenceError("unknown fence")
        epoch = row["epoch"]
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
            raise ConsistencyCorruptionError("epoch must be persisted >= 1")
        return FenceToken(
            tenant_id=tenant,
            resource_id=resource,
            epoch=epoch,
            writer_id=_canonical_text(row["writer_id"], "writer_id"),
            updated_at=_parse_time(row["updated_at"], "updated_at"),
        )

    def card(self) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM consistency_fence WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        return {
            "kind": "consistency_fence",
            "hit": True,
            "law": "tenant-epoch-cas",
            "citation": "VOL-132",
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
            "fence_count": int(row["n"]),
        }

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteConsistencyFence":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
