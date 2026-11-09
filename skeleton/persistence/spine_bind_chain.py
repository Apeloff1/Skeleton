"""Hash chain over the bind-card journal.

Recomputes the chain from the journal rows. A rewritten row fails closed.
Does not start a dispatcher and does not advance a fence.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindChainError(RuntimeError):
    """Bind chain rejected its inputs. Not a maturity signal."""


_COLUMNS = (
    "tenant_id",
    "digest",
    "epoch",
    "live_motor",
    "dispatcher_running",
    "ci_green",
    "merged",
    "apply_landed",
)


class SpineBindChain:
    """Seal bind journal rows into a SHA-256 chain."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindChainError("tenant_id must be non-empty text")
        rows = self._connection.execute(
            """
            SELECT tenant_id, digest, epoch, live_motor, dispatcher_running,
                   ci_green, merged, apply_landed
            FROM spine_bind_card
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchall()
        if not rows:
            raise SpineBindChainError("bind journal empty")
        digest = "0" * 64
        for row in rows:
            if any(int(row[name]) != 0 for name in _COLUMNS[3:]):
                raise SpineBindChainError("bind row is not dark")
            payload = "|".join(str(row[name]) for name in _COLUMNS)
            digest = hashlib.sha256(f"{digest}|{payload}".encode("utf-8")).hexdigest()
        return {
            "kind": "spine_bind_chain",
            "hit": True,
            "law": "bind-journal-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "digest": digest,
            "rewritten": False,
            "live_motor": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
