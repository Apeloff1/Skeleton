"""Tenant isolation witness for poison apply.

Counts apply rows for one tenant. A foreign tenant id returns zero. It does
not accept a delivery and it does not advance a fence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpinePoisonWitnessError(RuntimeError):
    """Witness rejected its inputs. Not a maturity signal."""


class SpinePoisonWitness:
    """Read the poison-apply journal for one tenant."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpinePoisonWitnessError("tenant_id must be non-empty text")
        row = self._connection.execute(
            """
            SELECT
                COUNT(*) AS seen,
                COALESCE(SUM(applied), 0) AS applied
            FROM spine_poison_apply
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()
        return {
            "kind": "spine_poison_witness",
            "hit": True,
            "law": "tenant-isolated-journal",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": int(row["seen"]),
            "applied": int(row["applied"]),
            "applied_fence": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
