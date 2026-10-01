"""Hold record for poison that is not applied.

Stores the reason. Does not accept a delivery and does not advance a fence.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SpineHoldError(RuntimeError):
    """Hold rejected its inputs. Not a maturity signal."""


class SpineHold:
    """Append a hold row. applied stays 0."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_hold (
                hold_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                held_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def hold(self, *, tenant_id: str, outbox_id: str, reason: str, now: datetime | None = None) -> dict[str, Any]:
        if not all(isinstance(value, str) and value.strip() for value in (tenant_id, outbox_id, reason)):
            raise SpineHoldError("tenant_id, outbox_id, and reason must be non-empty text")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineHoldError("now must be timezone-aware")
        self._connection.execute(
            "INSERT INTO spine_hold(tenant_id, outbox_id, reason, held_at) VALUES (?, ?, ?, ?)",
            (tenant_id, outbox_id, reason, instant.isoformat()),
        )
        self._connection.commit()
        return {
            "kind": "spine_hold",
            "hit": True,
            "law": "hold-does-not-apply",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "reason": reason,
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
