"""Append-only journal for a bind card.

Stores one digest per tenant. A second write with a different digest fails
closed. The journal does not start a dispatcher and does not import Motor.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindJournalError(RuntimeError):
    """Bind journal rejected its inputs. Not a maturity signal."""


class SpineBindJournal:
    """Seal a bind card. Do not rewrite it."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_bind_card (
                tenant_id TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                live_motor INTEGER NOT NULL,
                dispatcher_running INTEGER NOT NULL,
                ci_green INTEGER NOT NULL,
                merged INTEGER NOT NULL,
                apply_landed INTEGER NOT NULL
            )
            """
        )
        self._connection.commit()

    def append(self, tenant_id: str, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindJournalError("tenant_id must be non-empty text")
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_card":
            raise SpineBindJournalError("card must be a spine_bind_card")
        if card.get("tenant_id") != tenant_id:
            raise SpineBindJournalError("bind card tenant does not match")
        if card.get("hit") is not False or card.get("moved") is not False:
            raise SpineBindJournalError("bind card is not dark")
        for flag in ("live_motor", "dispatcher_running", "ci_green", "merged", "apply_landed"):
            if card.get(flag) is not False:
                raise SpineBindJournalError("bind card is not dark")
        epoch = card.get("epoch_before")
        if not isinstance(epoch, int) or epoch < 0 or epoch != card.get("epoch_after"):
            raise SpineBindJournalError("bind card epoch moved")
        digest = card.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindJournalError("bind card digest missing")
        expected = hashlib.sha256(
            json.dumps(
                {key: value for key, value in card.items() if key != "digest"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if digest != expected:
            raise SpineBindJournalError("bind card digest mismatch")
        existing = self._connection.execute(
            "SELECT digest FROM spine_bind_card WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if existing is not None and existing["digest"] != digest:
            raise SpineBindJournalError("bind journal rewrite")
        if existing is None:
            self._connection.execute(
                """
                INSERT INTO spine_bind_card (
                    tenant_id, digest, epoch, live_motor, dispatcher_running,
                    ci_green, merged, apply_landed
                ) VALUES (?, ?, ?, 0, 0, 0, 0, 0)
                """,
                (tenant_id, digest, epoch),
            )
            self._connection.commit()
        return {
            "kind": "spine_bind_journal",
            "hit": True,
            "law": "bind-card-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "digest": digest,
            "epoch": epoch,
            "rewritten": False,
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

    def read(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindJournalError("tenant_id must be non-empty text")
        row = self._connection.execute(
            "SELECT digest, epoch FROM spine_bind_card WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return {
            "kind": "spine_bind_journal",
            "hit": row is not None,
            "law": "bind-card-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": row is not None,
            "digest": None if row is None else row["digest"],
            "epoch": None if row is None else int(row["epoch"]),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
