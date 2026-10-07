"""Mongo inbox parity for the P2 runtime spine.

The class depends on an injected database protocol, not Motor or PyMongo.
A deployment can pass an AsyncIOMotorDatabase. Tests pass a dict-backed fake.
Accept rules match the SQLite ledger: exactly-once identity, contiguous
versions, tenant binding, and digest conflicts. This does not sign work off.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.inbox_ledger import (
    InboxAcceptResult,
    InboxConflict,
    InboxDelivery,
    InboxReceipt,
)


class MongoInboxError(RuntimeError):
    """Mongo inbox input cannot be stored. Not a maturity signal."""


class _MemoryCollection:
    """Small protocol stand-in used when a caller has no driver."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append(dict(doc))

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return
        raise MongoInboxError("watermark update missed its row")


class MongoInboxLedger:
    """Exactly-once inbox over injected Mongo collections."""

    def __init__(self, database: Any, *, namespace: str = "operation_inbox") -> None:
        if not isinstance(namespace, str) or not namespace.strip() or namespace != namespace.strip():
            raise MongoInboxError("namespace must be canonical text")
        self.namespace = namespace
        if database is None:
            self.receipts = _MemoryCollection()
            self.watermarks = _MemoryCollection()
        else:
            self.receipts = database[f"{namespace}_receipts"]
            self.watermarks = database[f"{namespace}_watermarks"]

    def accept(
        self,
        delivery: InboxDelivery,
        *,
        consumer_id: str,
        now: datetime | None = None,
    ) -> InboxAcceptResult:
        if not isinstance(delivery, InboxDelivery):
            raise TypeError("delivery must be an InboxDelivery")
        if not isinstance(consumer_id, str) or not consumer_id.strip():
            raise MongoInboxError("consumer_id must be non-empty text")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise MongoInboxError("now must be timezone-aware")
        if delivery.published_at < delivery.created_at:
            raise InboxConflict("publication receipt cannot predate event creation")
        if instant < delivery.published_at:
            raise InboxConflict("inbox accept cannot predate publication")
        digest = delivery.digest()
        existing = self.receipts.find_one(
            {
                "namespace": self.namespace,
                "consumer_id": consumer_id,
                "event_id": delivery.event_id,
            }
        )
        if existing is not None:
            if (
                existing["payload_digest"] != digest
                or existing["tenant_id"] != delivery.tenant_id
                or existing["operation_id"] != delivery.operation_id
                or existing["operation_version"] != delivery.operation_version
                or existing["event_type"] != delivery.event_type
            ):
                raise InboxConflict("event identity already accepted with different content")
            watermark = self._applied(consumer_id, delivery.operation_id)
            return InboxAcceptResult(
                receipt=self._receipt(existing),
                applied_through=watermark,
                duplicate=True,
            )
        bound = self.watermarks.find_one(
            {
                "namespace": self.namespace,
                "consumer_id": consumer_id,
                "operation_id": delivery.operation_id,
            }
        )
        if bound is None:
            if delivery.operation_version != 1:
                raise InboxConflict("first inbox accept must be operation version 1")
        else:
            if bound["tenant_id"] != delivery.tenant_id:
                raise InboxConflict("operation watermark is bound to another tenant")
            if delivery.operation_version != int(bound["applied_through"]) + 1:
                raise InboxConflict("inbox version must be contiguous with the consumer watermark")
        doc = {
            "namespace": self.namespace,
            "consumer_id": consumer_id,
            "event_id": delivery.event_id,
            "operation_id": delivery.operation_id,
            "operation_version": delivery.operation_version,
            "tenant_id": delivery.tenant_id,
            "event_type": delivery.event_type,
            "payload_digest": digest,
            "created_at": delivery.created_at.isoformat(),
            "accepted_at": instant.isoformat(),
        }
        self.receipts.insert_one(doc)
        if bound is None:
            self.watermarks.insert_one(
                {
                    "namespace": self.namespace,
                    "consumer_id": consumer_id,
                    "operation_id": delivery.operation_id,
                    "tenant_id": delivery.tenant_id,
                    "applied_through": delivery.operation_version,
                    "updated_at": instant.isoformat(),
                }
            )
        else:
            self.watermarks.update_one(
                {
                    "namespace": self.namespace,
                    "consumer_id": consumer_id,
                    "operation_id": delivery.operation_id,
                },
                {"$set": {"applied_through": delivery.operation_version, "updated_at": instant.isoformat()}},
            )
        return InboxAcceptResult(
            receipt=self._receipt(doc),
            applied_through=delivery.operation_version,
            duplicate=False,
        )

    def _applied(self, consumer_id: str, operation_id: str) -> int:
        row = self.watermarks.find_one(
            {
                "namespace": self.namespace,
                "consumer_id": consumer_id,
                "operation_id": operation_id,
            }
        )
        if row is None:
            return 0
        return int(row["applied_through"])

    @staticmethod
    def _receipt(doc: dict[str, Any]) -> InboxReceipt:
        return InboxReceipt(
            consumer_id=doc["consumer_id"],
            event_id=doc["event_id"],
            operation_id=doc["operation_id"],
            operation_version=int(doc["operation_version"]),
            tenant_id=doc["tenant_id"],
            event_type=doc["event_type"],
            payload_digest=doc["payload_digest"],
            created_at=datetime.fromisoformat(doc["created_at"]),
            accepted_at=datetime.fromisoformat(doc["accepted_at"]),
        )

    def card(self) -> dict[str, Any]:
        return {
            "kind": "mongo_inbox",
            "hit": True,
            "law": "exactly-once-inbox",
            "citation": "VOL-134",
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
