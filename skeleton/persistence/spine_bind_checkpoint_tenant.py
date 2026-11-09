"""Tenant-isolation read for bind recovery checkpoints."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


class SpineBindCheckpointTenantError(RuntimeError):
    """Checkpoint tenant read rejected its inputs. Not a maturity signal."""


class SpineBindCheckpointTenant:
    """Read only the requested tenant; foreign tenants stay invisible."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindCheckpointTenantError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT tenant_id, recovery_digest
                FROM spine_bind_checkpoint
                WHERE tenant_id = ?
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindCheckpointTenantError("checkpoint journal missing") from exc
        if any(row["tenant_id"] != tenant_id for row in rows):
            raise SpineBindCheckpointTenantError("foreign checkpoint leaked")
        return {
            "kind": "spine_bind_checkpoint_tenant",
            "hit": bool(rows),
            "law": "checkpoint-tenant-isolated",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "count": len(rows),
            "digests": [row["recovery_digest"] for row in rows],
            "foreign": 0,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
