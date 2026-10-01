"""Read a refused bind seal without rewriting it.

A foreign tenant is empty. A stored row with applied set or a moved epoch
fails closed. The reader does not accept a delivery.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldReadError(RuntimeError):
    """Bind hold read rejected its inputs. Not a maturity signal."""


class SpineBindHoldRead:
    """Count refusals. Do not apply."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str, outbox_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldReadError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldReadError("outbox_id must be non-empty text")
        try:
            row = self._connection.execute(
                """
                SELECT digest, applied, epoch FROM spine_bind_hold
                WHERE tenant_id = ? AND outbox_id = ?
                """,
                (tenant_id, outbox_id),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldReadError("bind hold journal missing") from exc
        if row is not None and int(row["applied"]) != 0:
            raise SpineBindHoldReadError("refusal row applied")
        return {
            "kind": "spine_bind_hold_read",
            "hit": False,
            "law": "bind-hold-stays-unapplied",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "seen": row is not None,
            "digest": None if row is None else row["digest"],
            "epoch": None if row is None else int(row["epoch"]),
            "applied": 0,
            "sealed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
