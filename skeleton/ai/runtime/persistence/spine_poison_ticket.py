"""Digest ticket bound to one hold row.

A ticket names the held outbox id and the expected digest. It does not accept
a delivery and it does not advance a fence. Consume is idempotent.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class SpinePoisonTicketError(RuntimeError):
    """Ticket rejected its inputs. Not a maturity signal."""


class SpinePoisonTicket:
    """Issue a digest ticket only when the hold row exists."""

    def __init__(self, hold_path: str | Path, path: str | Path) -> None:
        self._hold = sqlite3.connect(str(hold_path), check_same_thread=False)
        self._hold.row_factory = sqlite3.Row
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_poison_ticket (
                ticket_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                consumed INTEGER NOT NULL,
                issued_at TEXT NOT NULL
            )
            """
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
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpinePoisonTicketError("digest must be SHA-256 hex")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpinePoisonTicketError("now must be timezone-aware")
        hold = self._hold.execute(
            "SELECT 1 FROM spine_hold WHERE tenant_id = ? AND outbox_id = ?",
            (tenant_id, outbox_id),
        ).fetchone()
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
            INSERT INTO spine_poison_ticket(ticket_id, tenant_id, outbox_id, digest, consumed, issued_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (ticket_id, tenant_id, outbox_id, digest, instant.isoformat()),
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

    def consume(self, ticket_id: str, *, now: datetime | None = None) -> None:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpinePoisonTicketError("now must be timezone-aware")
        self._connection.execute(
            "UPDATE spine_poison_ticket SET consumed = consumed + 1 WHERE ticket_id = ?",
            (ticket_id,),
        )
        self._connection.commit()

    def close(self) -> None:
        self._hold.close()
        self._connection.close()
