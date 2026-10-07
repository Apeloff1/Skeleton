"""Append-only journal for a dark card.

Stores the card digest for one tenant. A second write with a different
digest fails closed. The journal does not start a dispatcher and does not
import Motor.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class SpineQuietError(RuntimeError):
    """Quiet journal rejected its inputs. Not a maturity signal."""


class SpineQuiet:
    """Seal a dark card. Do not rewrite it."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_quiet (
                tenant_id TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                live_motor INTEGER NOT NULL,
                merged INTEGER NOT NULL
            )
            """
        )
        self._connection.commit()

    def append(self, tenant_id: str, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineQuietError("tenant_id must be non-empty text")
        if not isinstance(card, dict) or card.get("kind") != "spine_dark":
            raise SpineQuietError("card must be a spine_dark card")
        if card.get("live_motor") is not False or card.get("merged") is not False:
            raise SpineQuietError("dark card is not dark")
        digest = hashlib.sha256(json.dumps(card, sort_keys=True).encode()).hexdigest()
        existing = self._connection.execute(
            "SELECT digest FROM spine_quiet WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if existing is not None and existing["digest"] != digest:
            raise SpineQuietError("quiet journal rewrite")
        if existing is None:
            self._connection.execute(
                "INSERT INTO spine_quiet (tenant_id, digest, live_motor, merged) VALUES (?, ?, 0, 0)",
                (tenant_id, digest),
            )
            self._connection.commit()
        return {
            "kind": "spine_quiet",
            "hit": True,
            "law": "dark-card-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "digest": digest,
            "rewritten": False,
            "live_motor": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def read(self, tenant_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT digest FROM spine_quiet WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return {
            "kind": "spine_quiet",
            "hit": row is not None,
            "law": "dark-card-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": row is not None,
            "digest": None if row is None else row["digest"],
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
