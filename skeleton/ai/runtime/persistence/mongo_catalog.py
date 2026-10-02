"""Tenant catalog for the Mongo fence. Read only."""

from __future__ import annotations

from typing import Any

from skeleton.persistence.mongo_fence import MongoConsistencyFence


class MongoCatalogError(RuntimeError):
    """Mongo catalog rejected its inputs. Not a maturity signal."""


class MongoCatalog:
    """List Mongo fence rows for one tenant."""

    def __init__(self, fence: MongoConsistencyFence) -> None:
        if not isinstance(fence, MongoConsistencyFence):
            raise MongoCatalogError("fence must be a MongoConsistencyFence")
        self.fence = fence

    def list(self, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise MongoCatalogError("tenant_id must be non-empty text")
        docs = getattr(self.fence.rows, "docs", None)
        if docs is None:
            raise MongoCatalogError("catalog requires the in-memory row protocol")
        rows = [
            doc for doc in docs
            if doc.get("namespace") == self.fence.namespace and doc.get("tenant_id") == tenant_id
        ]
        rows.sort(key=lambda doc: str(doc.get("resource_id")))
        return tuple(
            {
                "resource_id": doc["resource_id"],
                "epoch": int(doc["epoch"]),
                "writer_id": doc["writer_id"],
            }
            for doc in rows
        )

    def card(self, *, tenant_id: str) -> dict[str, Any]:
        rows = self.list(tenant_id=tenant_id)
        return {
            "kind": "mongo_catalog",
            "hit": True,
            "law": "tenant-fence-catalog",
            "citation": "VOL-132",
            "tenant_id": tenant_id,
            "count": len(rows),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
