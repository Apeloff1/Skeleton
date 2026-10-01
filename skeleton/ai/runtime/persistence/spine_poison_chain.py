"""Hash chain over the poison-apply journal.

Recomputes the chain from the journal rows. A rewritten row fails closed.
Does not accept a delivery and does not advance a fence.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


class SpinePoisonChainError(RuntimeError):
    """Chain rejected its inputs. Not a maturity signal."""


class SpinePoisonChain:
    """Seal tenant journal rows into a SHA-256 chain."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpinePoisonChainError("tenant_id must be non-empty text")
        rows = self._connection.execute(
            """
            SELECT apply_id, tenant_id, outbox_id, digest, reason,
                   epoch_before, epoch_after, applied, ticket_id
            FROM spine_poison_apply
            WHERE tenant_id = ?
            ORDER BY apply_id
            """,
            (tenant_id,),
        ).fetchall()
        digest = "0" * 64
        for row in rows:
            payload = "|".join(
                str(row[name])
                for name in (
                    "apply_id",
                    "tenant_id",
                    "outbox_id",
                    "digest",
                    "reason",
                    "epoch_before",
                    "epoch_after",
                    "applied",
                    "ticket_id",
                )
            )
            digest = hashlib.sha256(f"{digest}|{payload}".encode("utf-8")).hexdigest()
        return {
            "kind": "spine_poison_chain",
            "hit": True,
            "law": "journal-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "chain": digest,
            "applied_fence": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def verify(self, tenant_id: str, expected: str) -> dict[str, Any]:
        card = self.seal(tenant_id)
        card["match"] = card["chain"] == expected
        card["hit"] = card["match"]
        if not card["match"]:
            card["reason"] = "chain-mismatch"
        return card

    def close(self) -> None:
        self._connection.close()
