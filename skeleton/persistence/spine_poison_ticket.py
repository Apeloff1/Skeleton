"""Digest ticket bound to one hold row.

A ticket names the held outbox id and the expected digest. It does not accept
a delivery and it does not advance a fence. Consume is idempotent.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from skeleton.persistence.spine_hold import (
    _active_spine_hold,
    _ensure_spine_hold_schema,
)


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpinePoisonTicketError(RuntimeError):
    """Ticket rejected its inputs. Not a maturity signal."""


class SpinePoisonTicket:
    """Issue a digest ticket only when the hold row exists."""

    def __init__(self, hold_path: str | Path, path: str | Path) -> None:
        self._hold = sqlite3.connect(str(hold_path), check_same_thread=False)
        self._hold.row_factory = sqlite3.Row
        _ensure_spine_hold_schema(self._hold)
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_poison_ticket (
                ticket_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                hold_id INTEGER NOT NULL,
                digest TEXT NOT NULL,
                consumed INTEGER NOT NULL,
                issued_at TEXT NOT NULL
            )
            """
        )
        columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(spine_poison_ticket)"
            )
        }
        if "hold_id" not in columns:
            self._connection.execute(
                "ALTER TABLE spine_poison_ticket ADD COLUMN hold_id INTEGER"
            )
        self._connection.commit()

    def issue(
        self,
        *,
        tenant_id: str,
        outbox_id: str,
        digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not all(isinstance(value, str) and value.strip() for value in (tenant_id, outbox_id)):
            raise SpinePoisonTicketError("tenant_id and outbox_id must be non-empty text")
        if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
            raise SpinePoisonTicketError("digest must be lowercase SHA-256 hex")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpinePoisonTicketError("now must be timezone-aware")
        hold = _active_spine_hold(
            self._hold,
            tenant_id=tenant_id,
            outbox_id=outbox_id,
        )
        if hold is None:
            return {
                "kind": "spine_poison_ticket",
                "hit": False,
                "law": "ticket-requires-hold",
                "citation": "VOL-134",
                "reason": "unheld",
                "issued": 0,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }
        ticket_id = str(uuid4())
        self._connection.execute(
            """
            INSERT INTO spine_poison_ticket(
                ticket_id, tenant_id, outbox_id, hold_id, digest,
                consumed, issued_at
            )
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                ticket_id,
                tenant_id,
                outbox_id,
                int(hold["hold_id"]),
                digest,
                instant.isoformat(),
            ),
        )
        self._connection.commit()
        return {
            "kind": "spine_poison_ticket",
            "hit": True,
            "law": "ticket-requires-hold",
            "citation": "VOL-134",
            "ticket_id": ticket_id,
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "hold_id": int(hold["hold_id"]),
            "digest": digest,
            "issued": 1,
            "consumed": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def read(self, ticket_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM spine_poison_ticket WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()

    def hold_release_state(self, ticket_id: str) -> dict[str, int] | None:
        ticket = self.read(ticket_id)
        if ticket is None:
            return None
        hold_id = ticket["hold_id"]
        if isinstance(hold_id, bool) or not isinstance(hold_id, int) or hold_id < 1:
            return None
        row = self._hold.execute(
            """
            SELECT
                COUNT(*) AS target_rows,
                COALESCE(
                    SUM(CASE WHEN released = 0 THEN 1 ELSE 0 END),
                    0
                ) AS target_active,
                COALESCE(
                    SUM(
                        CASE
                            WHEN released = 1 AND release_ticket_id = ?
                            THEN 1 ELSE 0
                        END
                    ),
                    0
                ) AS released_by_ticket
            FROM spine_hold
            WHERE hold_id = ?
              AND tenant_id = ?
              AND outbox_id = ?
            """,
            (
                ticket_id,
                hold_id,
                ticket["tenant_id"],
                ticket["outbox_id"],
            ),
        ).fetchone()
        return {
            "target_rows": int(row["target_rows"]),
            "target_active": int(row["target_active"]),
            "released_by_ticket": int(row["released_by_ticket"]),
        }

    def consume(self, ticket_id: str, *, now: datetime | None = None) -> bool:
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            raise SpinePoisonTicketError("ticket_id must be non-empty text")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpinePoisonTicketError("now must be timezone-aware")
        connection = self._connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE spine_poison_ticket
                SET consumed = 1
                WHERE ticket_id = ? AND consumed = 0
                """,
                (ticket_id,),
            )
            claimed = cursor.rowcount == 1
            connection.commit()
            return claimed
        except Exception:
            connection.rollback()
            raise

    def close(self) -> None:
        self._hold.close()
        self._connection.close()
