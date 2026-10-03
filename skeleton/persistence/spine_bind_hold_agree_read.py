"""Read an agree row without rewriting it.

A foreign tenant is empty. A stored row with released or consumed set fails
closed. The reader does not release a hold.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldAgreeReadError(RuntimeError):
    """Agree read rejected its inputs. Not a maturity signal."""


class SpineBindHoldAgreeRead:
    """Count agree rows. Do not apply."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str, outbox_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldAgreeReadError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldAgreeReadError("outbox_id must be non-empty text")
        try:
            row = self._connection.execute(
                """
                SELECT digest, released, consumed, epoch FROM spine_bind_hold_agree
                WHERE tenant_id = ? AND outbox_id = ?
                """,
                (tenant_id, outbox_id),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldAgreeReadError("agree journal missing") from exc
        if row is not None and (int(row["released"]) != 0 or int(row["consumed"]) != 0):
            raise SpineBindHoldAgreeReadError("agree row is not dark")
        return {
            "kind": "spine_bind_hold_agree_read",
            "hit": False,
            "law": "agree-row-stays-dark",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "seen": row is not None,
            "digest": None if row is None else row["digest"],
            "epoch": None if row is None else int(row["epoch"]),
            "released": False,
            "consumed": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
