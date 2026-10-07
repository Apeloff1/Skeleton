"""Read the bind journal without appending.

A foreign tenant is empty. A stored row with a lit flag fails closed.
The reader does not rewrite the digest and does not advance a fence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindReadError(RuntimeError):
    """Bind read rejected its inputs. Not a maturity signal."""


class SpineBindRead:
    """Count dark bind rows. Do not append."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindReadError("tenant_id must be non-empty text")
        row = self._connection.execute(
            """
            SELECT digest, epoch, live_motor, dispatcher_running, ci_green, merged, apply_landed
            FROM spine_bind_card
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()
        if row is not None and any(
            int(row[name]) != 0
            for name in ("live_motor", "dispatcher_running", "ci_green", "merged", "apply_landed")
        ):
            raise SpineBindReadError("bind row is not dark")
        return {
            "kind": "spine_bind_read",
            "hit": False,
            "law": "bind-row-stays-dark",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": row is not None,
            "digest": None if row is None else row["digest"],
            "epoch": None if row is None else int(row["epoch"]),
            "moved": False,
            "live_motor": False,
            "dispatcher_running": False,
            "ci_green": False,
            "merged": False,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
