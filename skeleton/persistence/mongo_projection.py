"""Project published outbox rows into the Mongo inbox and Mongo fence.

The SQLite store remains the publisher. This binder does not import Motor and
does not sign work off. A conflict is counted and does not advance the fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.consistency_fence import ConsistencyConflict, ConsistencyFenceError
from skeleton.persistence.inbox_ledger import InboxConflict, delivery_from_outbox
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.mongo_inbox import MongoInboxLedger
from skeleton.persistence.operation_store import SQLiteOperationStore


class MongoProjectionError(RuntimeError):
    """Mongo projection rejected its inputs. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class MongoProjectionReport:
    scanned: int
    applied: int
    duplicates: int
    poisoned: int
    fence_advances: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "mongo_projection",
            "hit": self.poisoned == 0,
            "law": "published-outbox-to-mongo-fence",
            "citation": "VOL-134",
            "scanned": self.scanned,
            "applied": self.applied,
            "duplicates": self.duplicates,
            "poisoned": self.poisoned,
            "fence_advances": self.fence_advances,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


class MongoSpineProjection:
    """Consume acknowledged outbox rows into Mongo inbox and Mongo fence."""

    def __init__(
        self,
        operations: SQLiteOperationStore,
        inbox: MongoInboxLedger,
        fence: MongoConsistencyFence,
        *,
        consumer_id: str = "mongo-spine",
    ) -> None:
        if not isinstance(operations, SQLiteOperationStore):
            raise MongoProjectionError("operations must be a SQLiteOperationStore")
        if not isinstance(inbox, MongoInboxLedger):
            raise MongoProjectionError("inbox must be a MongoInboxLedger")
        if not isinstance(fence, MongoConsistencyFence):
            raise MongoProjectionError("fence must be a MongoConsistencyFence")
        self.operations = operations
        self.inbox = inbox
        self.fence = fence
        self.consumer_id = consumer_id
        self.poison: list[str] = []

    def project(self, *, limit: int = 100, now: datetime | None = None) -> MongoProjectionReport:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise MongoProjectionError("limit must be a positive integer")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise MongoProjectionError("now must be timezone-aware")
        events = self.operations.published_outbox(limit=limit)
        applied = duplicates = poisoned = advances = 0
        for event in events:
            stored = self.operations.get(event.operation_id)
            tenant_id = stored.envelope.tenant_id
            try:
                delivery = delivery_from_outbox(event, tenant_id)
                result = self.inbox.accept(delivery, consumer_id=self.consumer_id, now=event.published_at or instant)
            except InboxConflict:
                self.poison.append(event.outbox_id)
                poisoned += 1
                continue
            if result.duplicate:
                duplicates += 1
                continue
            resource = f"op:{event.operation_id}"
            try:
                expected = self.fence.read(tenant_id=tenant_id, resource_id=resource).epoch
            except ConsistencyFenceError:
                expected = 0
            try:
                self.fence.compare_and_advance(
                    tenant_id=tenant_id,
                    resource_id=resource,
                    expected_epoch=expected,
                    writer_id=self.consumer_id,
                    now=event.published_at or instant,
                )
            except ConsistencyConflict:
                self.poison.append(event.outbox_id)
                poisoned += 1
                continue
            applied += 1
            advances += 1
        return MongoProjectionReport(len(events), applied, duplicates, poisoned, advances)

    def card(self, report: MongoProjectionReport) -> dict[str, Any]:
        return report.as_dict()
