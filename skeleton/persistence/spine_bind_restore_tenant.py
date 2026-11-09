"""Tenant-isolation view of the anchored restore-receipt journal."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


class SpineBindRestoreTenantError(RuntimeError):
    """Restore tenant view rejected its input. Not a maturity signal."""


class SpineBindRestoreTenant:
    """Read only receipt rows belonging to the requested tenant."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreTenantError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT tenant_id, receipt_digest, row_digest
                FROM spine_bind_restore_receipt
                WHERE tenant_id = ?
                ORDER BY journal_id
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindRestoreTenantError("restore journal missing") from exc
        if any(row["tenant_id"] != tenant_id for row in rows):
            raise SpineBindRestoreTenantError("foreign restore receipt leaked")
        return {
            "kind": "spine_bind_restore_tenant",
            "hit": bool(rows),
            "law": "restore-journal-tenant-isolated",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "count": len(rows),
            "receipt_digests": [row["receipt_digest"] for row in rows],
            "row_digests": [row["row_digest"] for row in rows],
            "foreign": 0,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
