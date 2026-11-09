"""Append-only ledger of spine digests.

Stores the hash. Does not dispatch and does not advance a fence.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_digest import SpineDigest


class SpineLedgerError(RuntimeError):
    """Ledger rejected its inputs. Not a maturity signal."""


class SpineLedger:
    """Append digest cards for one operation."""

    def __init__(self, path: str | Path, digest: SpineDigest) -> None:
        if not isinstance(digest, SpineDigest):
            raise SpineLedgerError("digest must be a SpineDigest")
        self.digest = digest
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_digest_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def record(self, *, tenant_id: str, operation_id: str, now: datetime | None = None) -> dict[str, Any]:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineLedgerError("now must be timezone-aware")
        card = self.digest.read(tenant_id=tenant_id, operation_id=operation_id)
        self._connection.execute(
            """
            INSERT INTO spine_digest_ledger(tenant_id, operation_id, digest, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (tenant_id, operation_id, card["digest"], instant.isoformat()),
        )
        self._connection.commit()
        return {
            "kind": "spine_ledger",
            "hit": card["hit"],
            "law": "append-digest",
            "citation": "VOL-134",
            "digest": card["digest"],
            "count": self.count(tenant_id=tenant_id, operation_id=operation_id),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self, *, tenant_id: str, operation_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*) AS n FROM spine_digest_ledger
            WHERE tenant_id = ? AND operation_id = ?
            """,
            (tenant_id, operation_id),
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
