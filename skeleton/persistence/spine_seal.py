"""Seal journal for a cutover card.

Stores the card. Does not dispatch, does not advance a fence, and does not
set a completion checkbox.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_cutover import SpineCutover


class SpineSealError(RuntimeError):
    """Seal rejected its inputs. Not a maturity signal."""


class SpineSeal:
    """Append-only cutover snapshots."""

    def __init__(self, path: str | Path, cutover: SpineCutover) -> None:
        if not isinstance(cutover, SpineCutover):
            raise SpineSealError("cutover must be a SpineCutover")
        self.cutover = cutover
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_seal (
                seal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                sealed_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def seal(self, *, tenant_id: str, operation_id: str, now: datetime | None = None) -> dict[str, Any]:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineSealError("now must be timezone-aware")
        card = self.cutover.card(tenant_id=tenant_id, operation_id=operation_id)
        payload = json.dumps(card, sort_keys=True)
        cursor = self._connection.execute(
            """
            INSERT INTO spine_seal(tenant_id, operation_id, payload, sealed_at)
            VALUES (?, ?, ?, ?)
            """,
            (tenant_id, operation_id, payload, instant.isoformat()),
        )
        self._connection.commit()
        return {
            "kind": "spine_seal",
            "hit": card["hit"],
            "law": "cutover-snapshot",
            "citation": "VOL-134",
            "seal_id": int(cursor.lastrowid),
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS n FROM spine_seal").fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
