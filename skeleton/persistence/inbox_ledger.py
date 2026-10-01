"""Transactional inbox for published operation-outbox events.

VOL-134 inbox side of the P2 runtime spine. The ledger does not own
operation truth, does not compact the stream, and does not sign work off.
A consumer may accept a published outbox identity exactly once. The receipt
and the per-operation watermark commit in the same SQLite transaction.

Replays of the same event identity and payload digest are idempotent.
A reused event identity with a different digest, tenant, version, or type
is a conflict. Versions must be contiguous: the first accept is version 1,
and every later accept must be exactly applied_through + 1.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Mapping
from uuid import UUID


class InboxLedgerError(RuntimeError):
    """Base inbox failure. Not a maturity or sign-off signal."""


class InboxConflict(InboxLedgerError):
    """A durable inbox identity, tenant, or version fence was violated."""


class InboxCorruptionError(InboxLedgerError):
    """Persisted inbox state cannot be interpreted safely."""


_CONSUMER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_RESOURCE_TEXT_MAX = 256


def _canonical_text(value: object, field: str, *, max_length: int = _RESOURCE_TEXT_MAX) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InboxLedgerError(f"{field} must be non-empty text")
    if value != value.strip():
        raise InboxLedgerError(f"{field} must be canonical text")
    if len(value) > max_length:
        raise InboxLedgerError(f"{field} exceeds maximum length")
    return value


def _consumer_id(value: object) -> str:
    text = _canonical_text(value, "consumer_id", max_length=128)
    if not _CONSUMER_ID_RE.fullmatch(text):
        raise InboxLedgerError(
            "consumer_id must be 1-128 characters using A-Z a-z 0-9 . _ : -"
        )
    return text


def _canonical_uuid(value: object, field: str) -> str:
    text = _canonical_text(value, field, max_length=64)
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as exc:
        raise InboxLedgerError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != text:
        raise InboxLedgerError(f"{field} must be a canonical UUID")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InboxLedgerError(f"{field} must be an integer >= 1")
    return value


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise InboxLedgerError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InboxLedgerError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise InboxCorruptionError(f"{field} must be persisted as text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InboxCorruptionError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InboxCorruptionError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _persisted_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InboxCorruptionError(
            f"{field} must be persisted as an integer >= {minimum}"
        )
    return value


def canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or isinstance(payload, (str, bytes)):
        raise InboxLedgerError("payload must be a mapping")
    try:
        encoded = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise InboxLedgerError("payload is not a finite JSON object") from exc
    if not isinstance(decoded, dict):
        raise InboxLedgerError("payload must encode as a JSON object")
    return decoded


def payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        canonical_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class InboxDelivery:
    """Published outbox identity presented to one consumer."""

    event_id: str
    operation_id: str
    operation_version: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    published_at: datetime
    tenant_id: str

    def digest(self) -> str:
        return payload_digest(self.payload)


@dataclass(frozen=True, slots=True)
class InboxReceipt:
    consumer_id: str
    event_id: str
    operation_id: str
    operation_version: int
    tenant_id: str
    event_type: str
    payload_digest: str
    created_at: datetime
    accepted_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "consumer_id": self.consumer_id,
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "operation_version": self.operation_version,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "payload_digest": self.payload_digest,
            "created_at": self.created_at.isoformat(),
            "accepted_at": self.accepted_at.isoformat(),
            "stored_prose": 0,
            "completion_checkbox": False,
        }


@dataclass(frozen=True, slots=True)
class InboxAcceptResult:
    receipt: InboxReceipt
    applied_through: int
    duplicate: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.as_dict(),
            "applied_through": self.applied_through,
            "duplicate": self.duplicate,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


def delivery_from_outbox(event: Any, tenant_id: str) -> InboxDelivery:
    """Adapt a published OperationOutboxEvent without taking ownership of it."""

    published = getattr(event, "published_at", None)
    if published is None:
        raise InboxConflict("inbox refuses unpublished outbox events")
    payload = canonical_payload(getattr(event, "payload", {}))
    return InboxDelivery(
        event_id=_canonical_uuid(getattr(event, "outbox_id", None), "event_id"),
        operation_id=_canonical_uuid(getattr(event, "operation_id", None), "operation_id"),
        operation_version=_positive_int(
            getattr(event, "operation_version", None), "operation_version"
        ),
        event_type=_canonical_text(getattr(event, "event_type", None), "event_type"),
        payload=payload,
        created_at=_aware(getattr(event, "created_at", None), "created_at"),
        published_at=_aware(published, "published_at"),
        tenant_id=_canonical_text(tenant_id, "tenant_id"),
    )


class SQLiteInboxLedger:
    """SQLite exactly-once inbox over published outbox identities."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "operation_inbox",
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

                CREATE TABLE IF NOT EXISTS inbox_receipt (
                    namespace TEXT NOT NULL,
                    consumer_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    operation_version INTEGER NOT NULL,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    accepted_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, consumer_id, event_id)
                );

                CREATE TABLE IF NOT EXISTS inbox_watermark (
                    namespace TEXT NOT NULL,
                    consumer_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    applied_through INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, consumer_id, operation_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_inbox_receipt_version
                ON inbox_receipt(namespace, consumer_id, operation_id, operation_version);
                """
            )

    def accept(
        self,
        delivery: InboxDelivery,
        *,
        consumer_id: str,
        now: datetime | None = None,
    ) -> InboxAcceptResult:
        if not isinstance(delivery, InboxDelivery):
            raise TypeError("delivery must be an InboxDelivery")
        consumer = _consumer_id(consumer_id)
        event_id = _canonical_uuid(delivery.event_id, "event_id")
        operation_id = _canonical_uuid(delivery.operation_id, "operation_id")
        version = _positive_int(delivery.operation_version, "operation_version")
        event_type = _canonical_text(delivery.event_type, "event_type")
        tenant_id = _canonical_text(delivery.tenant_id, "tenant_id")
        created_at = _aware(delivery.created_at, "created_at")
        published_at = _aware(delivery.published_at, "published_at")
        if published_at < created_at:
            raise InboxConflict("publication receipt cannot predate event creation")
        digest = delivery.digest()
        instant = _aware(now or datetime.now(timezone.utc), "now")
        if instant < published_at:
            raise InboxConflict("inbox accept cannot predate publication")

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    """
                    SELECT *
                    FROM inbox_receipt
                    WHERE namespace = ? AND consumer_id = ? AND event_id = ?
                    """,
                    (self.namespace, consumer, event_id),
                ).fetchone()
                if existing is not None:
                    receipt = self._receipt_from_row(existing)
                    if (
                        receipt.payload_digest != digest
                        or receipt.tenant_id != tenant_id
                        or receipt.operation_id != operation_id
                        or receipt.operation_version != version
                        or receipt.event_type != event_type
                    ):
                        raise InboxConflict(
                            "event identity already accepted with different content"
                        )
                    watermark = self._watermark(consumer, operation_id)
                    self._connection.execute("COMMIT")
                    return InboxAcceptResult(
                        receipt=receipt,
                        applied_through=watermark,
                        duplicate=True,
                    )

                watermark_row = self._connection.execute(
                    """
                    SELECT tenant_id, applied_through
                    FROM inbox_watermark
                    WHERE namespace = ? AND consumer_id = ? AND operation_id = ?
                    """,
                    (self.namespace, consumer, operation_id),
                ).fetchone()
                if watermark_row is None:
                    if version != 1:
                        raise InboxConflict(
                            "first inbox accept must be operation version 1"
                        )
                else:
                    bound_tenant = watermark_row["tenant_id"]
                    if not isinstance(bound_tenant, str) or bound_tenant != tenant_id:
                        raise InboxConflict("operation watermark is bound to another tenant")
                    applied = _persisted_int(
                        watermark_row["applied_through"],
                        "applied_through",
                        minimum=1,
                    )
                    if version != applied + 1:
                        raise InboxConflict(
                            "inbox version must be contiguous with the consumer watermark"
                        )

                self._connection.execute(
                    """
                    INSERT INTO inbox_receipt(
                        namespace, consumer_id, event_id, operation_id,
                        operation_version, tenant_id, event_type,
                        payload_digest, created_at, accepted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        consumer,
                        event_id,
                        operation_id,
                        version,
                        tenant_id,
                        event_type,
                        digest,
                        created_at.isoformat(),
                        instant.isoformat(),
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO inbox_watermark(
                        namespace, consumer_id, operation_id, tenant_id,
                        applied_through, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, consumer_id, operation_id) DO UPDATE SET
                        applied_through = excluded.applied_through,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self.namespace,
                        consumer,
                        operation_id,
                        tenant_id,
                        version,
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

        return InboxAcceptResult(
            receipt=InboxReceipt(
                consumer_id=consumer,
                event_id=event_id,
                operation_id=operation_id,
                operation_version=version,
                tenant_id=tenant_id,
                event_type=event_type,
                payload_digest=digest,
                created_at=created_at,
                accepted_at=instant,
            ),
            applied_through=version,
            duplicate=False,
        )

    def get(self, consumer_id: str, event_id: str) -> InboxReceipt:
        consumer = _consumer_id(consumer_id)
        event = _canonical_uuid(event_id, "event_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT *
                FROM inbox_receipt
                WHERE namespace = ? AND consumer_id = ? AND event_id = ?
                """,
                (self.namespace, consumer, event),
            ).fetchone()
        if row is None:
            raise InboxLedgerError("unknown inbox receipt")
        return self._receipt_from_row(row)

    def applied_through(self, consumer_id: str, operation_id: str) -> int:
        return self._watermark(_consumer_id(consumer_id), _canonical_uuid(operation_id, "operation_id"))

    def applied_count(self, consumer_id: str | None = None) -> int:
        with self._lock:
            if consumer_id is None:
                row = self._connection.execute(
                    "SELECT COUNT(*) AS n FROM inbox_receipt WHERE namespace = ?",
                    (self.namespace,),
                ).fetchone()
            else:
                row = self._connection.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM inbox_receipt
                    WHERE namespace = ? AND consumer_id = ?
                    """,
                    (self.namespace, _consumer_id(consumer_id)),
                ).fetchone()
        return int(row["n"])

    def card(self) -> dict[str, Any]:
        return {
            "kind": "inbox_ledger",
            "hit": True,
            "law": "published-outbox-exactly-once",
            "citation": "VOL-134",
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
            "applied_count": self.applied_count(),
        }

    def _watermark(self, consumer_id: str, operation_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT applied_through
            FROM inbox_watermark
            WHERE namespace = ? AND consumer_id = ? AND operation_id = ?
            """,
            (self.namespace, consumer_id, operation_id),
        ).fetchone()
        if row is None:
            return 0
        return _persisted_int(row["applied_through"], "applied_through", minimum=1)

    @staticmethod
    def _receipt_from_row(row: sqlite3.Row) -> InboxReceipt:
        digest = row["payload_digest"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise InboxCorruptionError("payload_digest must be persisted SHA-256 hex")
        if any(ch not in "0123456789abcdef" for ch in digest):
            raise InboxCorruptionError("payload_digest must be lowercase SHA-256 hex")
        return InboxReceipt(
            consumer_id=_consumer_id(row["consumer_id"]),
            event_id=_canonical_uuid(row["event_id"], "event_id"),
            operation_id=_canonical_uuid(row["operation_id"], "operation_id"]),
            operation_version=_persisted_int(
                row["operation_version"], "operation_version", minimum=1
            ),
            tenant_id=_canonical_text(row["tenant_id"], "tenant_id"),
            event_type=_canonical_text(row["event_type"], "event_type"),
            payload_digest=digest,
            created_at=_parse_time(row["created_at"], "created_at"),
            accepted_at=_parse_time(row["accepted_at"], "accepted_at"]),
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteInboxLedger":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
