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


def _ensure_spine_hold_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS spine_hold (
            hold_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            outbox_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            held_at TEXT NOT NULL,
            released INTEGER NOT NULL DEFAULT 0,
            released_at TEXT,
            release_ticket_id TEXT
        )
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(spine_hold)")
    }
    if "released" not in columns:
        connection.execute(
            "ALTER TABLE spine_hold ADD COLUMN released INTEGER NOT NULL DEFAULT 0"
        )
    if "released_at" not in columns:
        connection.execute(
            "ALTER TABLE spine_hold ADD COLUMN released_at TEXT"
        )
    if "release_ticket_id" not in columns:
        connection.execute(
            "ALTER TABLE spine_hold ADD COLUMN release_ticket_id TEXT"
        )
    connection.commit()


def _active_spine_hold(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    outbox_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT hold_id, reason
        FROM spine_hold
        WHERE tenant_id = ? AND outbox_id = ? AND released = 0
        ORDER BY hold_id DESC
        LIMIT 1
        """,
        (tenant_id, outbox_id),
    ).fetchone()


def _release_spine_hold(
    connection: sqlite3.Connection,
    *,
    hold_id: int,
    tenant_id: str,
    outbox_id: str,
    ticket_id: str,
    released_at: str,
) -> int:
    cursor = connection.execute(
        """
        UPDATE spine_hold
        SET released = 1,
            released_at = ?,
            release_ticket_id = ?
        WHERE hold_id = ?
          AND tenant_id = ?
          AND outbox_id = ?
          AND released = 0
        """,
        (
            released_at,
            ticket_id,
            hold_id,
            tenant_id,
            outbox_id,
        ),
    )
    connection.commit()
    return max(0, cursor.rowcount)


class SpineHold:
    """Append immutable hold evidence and retain auditable release metadata."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        _ensure_spine_hold_schema(self._connection)

    def hold(self, *, tenant_id: str, outbox_id: str, reason: str, now: datetime | None = None) -> dict[str, Any]:
        if not all(isinstance(value, str) and value.strip() for value in (tenant_id, outbox_id, reason)):
            raise SpineHoldError("tenant_id, outbox_id, and reason must be non-empty text")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineHoldError("now must be timezone-aware")
        self._connection.execute(
            """
            INSERT INTO spine_hold(
                tenant_id, outbox_id, reason, held_at, released
            ) VALUES (?, ?, ?, ?, 0)
            """,
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
            "released": 0,
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
