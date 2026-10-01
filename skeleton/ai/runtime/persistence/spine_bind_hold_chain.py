"""Hash chain over the bind-hold refusal journal.

Recomputes the chain from the tenant rows. A rewritten row fails closed.
Does not accept a delivery and does not advance a fence.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldChainError(RuntimeError):
    """Bind hold chain rejected its inputs. Not a maturity signal."""


class SpineBindHoldChain:
    """Seal refusal rows into a SHA-256 chain."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldChainError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT tenant_id, outbox_id, digest, held, applied, epoch
                FROM spine_bind_hold
                WHERE tenant_id = ?
                ORDER BY outbox_id
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldChainError("bind hold journal missing") from exc
        digest = "0" * 64
        for row in rows:
            if int(row["applied"]) != 0 or int(row["held"]) != 1:
                raise SpineBindHoldChainError("refusal row is not dark")
            payload = "|".join(
                str(row[name]) for name in ("tenant_id", "outbox_id", "digest", "held", "applied", "epoch")
            )
            digest = hashlib.sha256(f"{digest}|{payload}".encode("utf-8")).hexdigest()
        return {
            "kind": "spine_bind_hold_chain",
            "hit": True,
            "law": "bind-hold-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "digest": digest,
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
