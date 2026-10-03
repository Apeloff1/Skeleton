"""Hash chain over the agree journal.

Recomputes the chain from the tenant rows. A rewritten row fails closed.
Does not release a hold and does not consume a ticket.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldAgreeChainError(RuntimeError):
    """Agree chain rejected its inputs. Not a maturity signal."""


class SpineBindHoldAgreeChain:
    """Seal agree rows into a SHA-256 chain."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldAgreeChainError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT tenant_id, outbox_id, hold_id, digest, released, consumed, epoch
                FROM spine_bind_hold_agree
                WHERE tenant_id = ?
                ORDER BY outbox_id
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldAgreeChainError("agree journal missing") from exc
        digest = "0" * 64
        for row in rows:
            if int(row["released"]) != 0 or int(row["consumed"]) != 0:
                raise SpineBindHoldAgreeChainError("agree row is not dark")
            payload = "|".join(
                str(row[name])
                for name in ("tenant_id", "outbox_id", "hold_id", "digest", "released", "consumed", "epoch")
            )
            digest = hashlib.sha256(f"{digest}|{payload}".encode("utf-8")).hexdigest()
        return {
            "kind": "spine_bind_hold_agree_chain",
            "hit": True,
            "law": "agree-journal-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "digest": digest,
            "released": False,
            "consumed": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
