"""Sequence gap reader for unread probe journals.

Reports missing sequence numbers for one tenant. A foreign tenant is empty,
not a gap of another tenant. Does not claim a surface and does not advance
a fence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineUnreadGapError(RuntimeError):
    """Unread gap read rejected its inputs. Not a maturity signal."""


class SpineUnreadGap:
    """Read missing sequence numbers from one probe table."""

    def __init__(self, journal_path: str | Path, *, table: str) -> None:
        if table not in {"spine_provider_probe", "spine_pr_probe"}:
            raise SpineUnreadGapError("table is not an unread probe journal")
        self._table = table
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def read(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineUnreadGapError("tenant_id must be non-empty text")
        rows = list(
            self._connection.execute(
                f"SELECT seq FROM {self._table} WHERE tenant_id = ? ORDER BY seq",
                (tenant_id,),
            )
        )
        seqs = [int(row["seq"]) for row in rows]
        missing: list[int] = []
        if seqs:
            expected = 1
            for seq in seqs:
                while expected < seq:
                    missing.append(expected)
                    expected += 1
                expected = seq + 1
        return {
            "kind": "spine_unread_gap",
            "hit": len(missing) == 0 and len(seqs) > 0,
            "law": "tenant-sequence-gap",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "table": self._table,
            "seen": seqs,
            "missing": missing,
            "green": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
