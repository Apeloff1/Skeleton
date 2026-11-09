"""Read the quiet journal without appending.

A foreign tenant is empty. A stored row with live_motor or merged set fails
closed. The witness does not rewrite the digest.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineQuietWitnessError(RuntimeError):
    """Quiet witness rejected its inputs. Not a maturity signal."""


class SpineQuietWitness:
    """Count dark rows. Do not append."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineQuietWitnessError("tenant_id must be non-empty text")
        row = self._connection.execute(
            "SELECT digest, live_motor, merged FROM spine_quiet WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is not None and (int(row["live_motor"]) != 0 or int(row["merged"]) != 0):
            raise SpineQuietWitnessError("quiet row is not dark")
        return {
            "kind": "spine_quiet_witness",
            "hit": row is not None,
            "law": "quiet-row-stays-dark",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": row is not None,
            "digest": None if row is None else row["digest"],
            "live_motor": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
