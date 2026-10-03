"""Append-only journal for an agree card.

Stores one digest per tenant and outbox id. A second write with a different
digest fails closed. The journal does not release a hold.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldAgreeJournalError(RuntimeError):
    """Agree journal rejected its inputs. Not a maturity signal."""


class SpineBindHoldAgreeJournal:
    """Seal an agree card. Do not rewrite it."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_bind_hold_agree (
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                hold_id INTEGER NOT NULL,
                digest TEXT NOT NULL,
                released INTEGER NOT NULL,
                consumed INTEGER NOT NULL,
                epoch INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, outbox_id)
            )
            """
        )
        self._connection.commit()

    def append(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_hold_agree":
            raise SpineBindHoldAgreeJournalError("card must be a spine_bind_hold_agree")
        if card.get("released") is not False or card.get("consumed") != 0 or card.get("moved") is not False:
            raise SpineBindHoldAgreeJournalError("agree card is not dark")
        if card.get("applied") != 0 or card.get("sealed") is not False:
            raise SpineBindHoldAgreeJournalError("agree card is not dark")
        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        hold_id = card.get("hold_id")
        epoch = card.get("epoch")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldAgreeJournalError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldAgreeJournalError("outbox_id must be non-empty text")
        if not isinstance(hold_id, int) or hold_id < 1:
            raise SpineBindHoldAgreeJournalError("hold_id must be a positive int")
        if not isinstance(epoch, int) or epoch < 0:
            raise SpineBindHoldAgreeJournalError("epoch must be a non-negative int")
        digest = hashlib.sha256(
            json.dumps(card, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = self._connection.execute(
            "SELECT digest FROM spine_bind_hold_agree WHERE tenant_id = ? AND outbox_id = ?",
            (tenant_id, outbox_id),
        ).fetchone()
        if existing is not None and existing["digest"] != digest:
            raise SpineBindHoldAgreeJournalError("agree journal rewrite")
        if existing is None:
            self._connection.execute(
                """
                INSERT INTO spine_bind_hold_agree (
                    tenant_id, outbox_id, hold_id, digest, released, consumed, epoch
                ) VALUES (?, ?, ?, ?, 0, 0, ?)
                """,
                (tenant_id, outbox_id, hold_id, digest, epoch),
            )
            self._connection.commit()
        return {
            "kind": "spine_bind_hold_agree_journal",
            "hit": True,
            "law": "agree-card-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "hold_id": hold_id,
            "digest": digest,
            "rewritten": False,
            "released": False,
            "consumed": 0,
            "epoch": epoch,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
