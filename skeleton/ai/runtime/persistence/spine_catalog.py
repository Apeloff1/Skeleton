"""Tenant fence catalog for the SQLite epoch fence.

Lists resources for one tenant. A foreign tenant sees an empty catalog, not
another tenant's epochs.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence


class SpineCatalogError(RuntimeError):
    """Catalog read rejected its inputs. Not a maturity signal."""


class SpineCatalog:
    """List fence resources owned by one tenant."""

    def __init__(self, fence: SQLiteConsistencyFence) -> None:
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineCatalogError("fence must be a SQLiteConsistencyFence")
        self.fence = fence

    def list(self, *, tenant_id: str) -> tuple[dict[str, Any], ...]:
        if not isinstance(tenant_id, str) or not tenant_id.strip() or tenant_id != tenant_id.strip():
            raise SpineCatalogError("tenant_id must be canonical text")
        with self.fence._lock:
            rows = self.fence._connection.execute(
                """
                SELECT resource_id, epoch, writer_id
                FROM consistency_fence
                WHERE namespace = ? AND tenant_id = ?
                ORDER BY resource_id ASC
                """,
                (self.fence.namespace, tenant_id),
            ).fetchall()
        return tuple(
            {
                "resource_id": row["resource_id"],
                "epoch": int(row["epoch"]),
                "writer_id": row["writer_id"],
            }
            for row in rows
        )

    def card(self, *, tenant_id: str) -> dict[str, Any]:
        rows = self.list(tenant_id=tenant_id)
        return {
            "kind": "spine_catalog",
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
