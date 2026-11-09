"""Mongo fence parity for the P2 runtime spine.

Injected database protocol. No Motor import. Compare-and-advance matches the
SQLite fence: missing fence opens at expected 0, a stale epoch conflicts, a
foreign tenant reads as unknown. This does not sign work off.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.consistency_fence import (
    ConsistencyConflict,
    ConsistencyFenceError,
    FenceToken,
)


class MongoFenceError(RuntimeError):
    """Mongo fence input cannot be stored. Not a maturity signal."""


class _Rows:
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
        raise MongoFenceError("fence update missed its row")


class MongoConsistencyFence:
    """Tenant epoch fence over injected collections."""

    def __init__(self, database: Any = None, *, namespace: str = "consistency_fence") -> None:
        if not isinstance(namespace, str) or not namespace.strip() or namespace != namespace.strip():
            raise MongoFenceError("namespace must be canonical text")
        self.namespace = namespace
        self.rows = _Rows() if database is None else database[f"{namespace}_rows"]

    def compare_and_advance(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        expected_epoch: int,
        writer_id: str,
        now: datetime | None = None,
    ) -> FenceToken:
        if not all(isinstance(value, str) and value.strip() for value in (tenant_id, resource_id, writer_id)):
            raise MongoFenceError("tenant, resource, and writer must be non-empty text")
        if isinstance(expected_epoch, bool) or not isinstance(expected_epoch, int) or expected_epoch < 0:
            raise MongoFenceError("expected_epoch must be a non-negative integer")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise MongoFenceError("now must be timezone-aware")
        query = {
            "namespace": self.namespace,
            "tenant_id": tenant_id,
            "resource_id": resource_id,
        }
        current = self.rows.find_one(query)
        if current is None:
            if expected_epoch != 0:
                raise ConsistencyConflict("unknown fence")
            epoch = 1
            self.rows.insert_one(
                {
                    **query,
                    "epoch": epoch,
                    "writer_id": writer_id,
                    "updated_at": instant.isoformat(),
                }
            )
        else:
            if int(current["epoch"]) != expected_epoch:
                raise ConsistencyConflict("stale fence epoch")
            updated = datetime.fromisoformat(current["updated_at"])
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if instant < updated:
                raise ConsistencyConflict("fence advance cannot predate current token")
            epoch = int(current["epoch"]) + 1
            self.rows.update_one(
                query,
                {"$set": {"epoch": epoch, "writer_id": writer_id, "updated_at": instant.isoformat()}},
            )
        return FenceToken(
            tenant_id=tenant_id,
            resource_id=resource_id,
            epoch=epoch,
            writer_id=writer_id,
            updated_at=instant,
        )

    def read(self, *, tenant_id: str, resource_id: str) -> FenceToken:
        row = self.rows.find_one(
            {
                "namespace": self.namespace,
                "tenant_id": tenant_id,
                "resource_id": resource_id,
            }
        )
        if row is None:
            raise ConsistencyFenceError("unknown fence")
        updated = datetime.fromisoformat(row["updated_at"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return FenceToken(
            tenant_id=tenant_id,
            resource_id=resource_id,
            epoch=int(row["epoch"]),
            writer_id=row["writer_id"],
            updated_at=updated,
        )

    def card(self) -> dict[str, Any]:
        return {
            "kind": "mongo_fence",
            "hit": True,
            "law": "tenant-epoch-cas",
            "citation": "VOL-132",
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
