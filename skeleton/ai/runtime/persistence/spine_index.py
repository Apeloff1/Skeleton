"""Index protocol for the Mongo spine collections.

Declares the indexes. Does not import Motor and does not create them unless
the injected database exposes create_index.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.mongo_inbox import MongoInboxLedger


class SpineIndexError(RuntimeError):
    """Index plan rejected its inputs. Not a maturity signal."""


INDEXES = (
    ("receipts", [("namespace", 1), ("consumer_id", 1), ("event_id", 1)], True),
    ("watermarks", [("namespace", 1), ("consumer_id", 1), ("operation_id", 1)], True),
    ("fence", [("namespace", 1), ("tenant_id", 1), ("resource_id", 1)], True),
)


class SpineIndexPlan:
    """List indexes and apply them only when the driver method exists."""

    def __init__(self, inbox: MongoInboxLedger, fence: MongoConsistencyFence) -> None:
        if not isinstance(inbox, MongoInboxLedger):
            raise SpineIndexError("inbox must be a MongoInboxLedger")
        if not isinstance(fence, MongoConsistencyFence):
            raise SpineIndexError("fence must be a MongoConsistencyFence")
        self.inbox = inbox
        self.fence = fence

    def plan(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"collection": name, "keys": keys, "unique": unique}
            for name, keys, unique in INDEXES
        )

    def apply(self) -> dict[str, Any]:
        created = 0
        skipped = 0
        targets = {
            "receipts": self.inbox.receipts,
            "watermarks": self.inbox.watermarks,
            "fence": self.fence.rows,
        }
        for name, keys, unique in INDEXES:
            target = targets[name]
            create = getattr(target, "create_index", None)
            if create is None:
                skipped += 1
                continue
            create(keys, unique=unique)
            created += 1
        return {
            "kind": "spine_index",
            "hit": True,
            "law": "index-when-driver-present",
            "citation": "VOL-134",
            "created": created,
            "skipped": skipped,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
