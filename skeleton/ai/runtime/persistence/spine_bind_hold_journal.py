"""Append-only journal of a refused bind seal.

Stores one digest per tenant and outbox id. A second write with a different
digest fails closed. applied stays 0. The journal does not accept a delivery.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldJournalError(RuntimeError):
    """Bind hold journal rejected its inputs. Not a maturity signal."""


class SpineBindHoldJournal:
    """Seal a refusal. Do not rewrite it."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_bind_hold (
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                held INTEGER NOT NULL,
                applied INTEGER NOT NULL,
                epoch INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, outbox_id)
            )
            """
        )
        self._connection.commit()

    def append(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_hold":
            raise SpineBindHoldJournalError("card must be a spine_bind_hold")
        if card.get("held") is not True or card.get("sealed") is not False:
            raise SpineBindHoldJournalError("refusal is not a hold")
        if card.get("applied") != 0 or card.get("moved") is not False:
            raise SpineBindHoldJournalError("refusal is not dark")
        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldJournalError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldJournalError("outbox_id must be non-empty text")
        epoch = card.get("epoch_before")
        if not isinstance(epoch, int) or epoch < 0 or epoch != card.get("epoch_after"):
            raise SpineBindHoldJournalError("refusal epoch moved")
        digest = hashlib.sha256(
            json.dumps(card, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = self._connection.execute(
            "SELECT digest FROM spine_bind_hold WHERE tenant_id = ? AND outbox_id = ?",
            (tenant_id, outbox_id),
        ).fetchone()
        if existing is not None and existing["digest"] != digest:
            raise SpineBindHoldJournalError("bind hold journal rewrite")
        if existing is None:
            self._connection.execute(
                """
                INSERT INTO spine_bind_hold (
                    tenant_id, outbox_id, digest, held, applied, epoch
                ) VALUES (?, ?, ?, 1, 0, ?)
                """,
                (tenant_id, outbox_id, digest, epoch),
            )
            self._connection.commit()
        return {
            "kind": "spine_bind_hold_journal",
            "hit": True,
            "law": "bind-hold-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "digest": digest,
            "rewritten": False,
            "applied": 0,
            "sealed": False,
            "epoch": epoch,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
