"""Tenant isolation over the bind journal.

A card for one tenant does not include another tenant's digest. A foreign
tenant is empty. The reader does not rewrite the journal and does not
advance a fence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindTenantError(RuntimeError):
    """Bind tenant read rejected its inputs. Not a maturity signal."""


class SpineBindTenant:
    """Prove a bind row stays inside its tenant."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str, other_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindTenantError("tenant_id must be non-empty text")
        if not isinstance(other_id, str) or not other_id.strip():
            raise SpineBindTenantError("other_id must be non-empty text")
        if tenant_id == other_id:
            raise SpineBindTenantError("other_id must be a foreign tenant")
        own = self._row(tenant_id)
        foreign = self._row(other_id)
        if foreign is not None:
            raise SpineBindTenantError("foreign tenant is not empty for this read")
        leaked = self._connection.execute(
            """
            SELECT tenant_id FROM spine_bind_card
            WHERE tenant_id != ? AND digest = ?
            """,
            (tenant_id, None if own is None else own["digest"]),
        ).fetchone()
        if own is not None and leaked is not None:
            raise SpineBindTenantError("bind digest leaked across tenants")
        return {
            "kind": "spine_bind_tenant",
            "hit": False,
            "law": "bind-tenant-isolated",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "other_id": other_id,
            "seen": own is not None,
            "foreign_seen": False,
            "digest": None if own is None else own["digest"],
            "epoch": None if own is None else int(own["epoch"]),
            "live_motor": False,
            "merged": False,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _row(self, tenant_id: str) -> sqlite3.Row | None:
        try:
            return self._connection.execute(
                "SELECT digest, epoch, live_motor, merged FROM spine_bind_card WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindTenantError("bind journal missing") from exc

    def close(self) -> None:
        self._connection.close()
