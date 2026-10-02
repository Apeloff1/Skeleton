"""Prove a bind refusal did not consume a poison ticket.

Reads ticket rows for the refused tenant and outbox id. A consumed ticket
fails closed. The proof does not issue a ticket and does not write consumed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldTicketError(RuntimeError):
    """Ticket proof rejected its inputs. Not a maturity signal."""


class SpineBindHoldTicket:
    """Count unconsumed tickets. Do not consume."""

    def __init__(self, ticket_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(ticket_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def prove(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_hold":
            raise SpineBindHoldTicketError("card must be a spine_bind_hold")
        if card.get("held") is not True or card.get("applied") != 0 or card.get("sealed") is not False:
            raise SpineBindHoldTicketError("refusal is not dark")
        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldTicketError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldTicketError("outbox_id must be non-empty text")
        table = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'spine_poison_ticket'"
        ).fetchone()
        tickets = 0
        consumed = 0
        if table is not None:
            rows = self._connection.execute(
                """
                SELECT consumed FROM spine_poison_ticket
                WHERE tenant_id = ? AND outbox_id = ?
                """,
                (tenant_id, outbox_id),
            ).fetchall()
            tickets = len(rows)
            consumed = sum(int(row["consumed"]) for row in rows)
        if consumed != 0:
            raise SpineBindHoldTicketError("refusal consumed a ticket")
        return {
            "kind": "spine_bind_hold_ticket",
            "hit": False,
            "law": "refusal-does-not-consume-ticket",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "tickets": tickets,
            "consumed": 0,
            "applied": 0,
            "sealed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
