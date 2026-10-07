"""Replay a sealed bind card without inserting a second row.

A matching digest leaves the row count and the epoch unchanged. A different
digest fails closed before any write. The replay does not start a dispatcher
and does not import Motor.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindReplayError(RuntimeError):
    """Bind replay rejected its inputs. Not a maturity signal."""


class SpineBindReplay:
    """Prove a second seal does not insert."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def replay(self, tenant_id: str, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindReplayError("tenant_id must be non-empty text")
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_card":
            raise SpineBindReplayError("card must be a spine_bind_card")
        if card.get("tenant_id") != tenant_id:
            raise SpineBindReplayError("bind card tenant does not match")
        if card.get("moved") is not False or card.get("apply_landed") is not False:
            raise SpineBindReplayError("bind card is not dark")
        digest = card.get("digest")
        epoch = card.get("epoch_before")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindReplayError("bind card digest missing")
        if not isinstance(epoch, int) or epoch < 0 or epoch != card.get("epoch_after"):
            raise SpineBindReplayError("bind card epoch moved")
        before = self._count(tenant_id)
        row = self._connection.execute(
            "SELECT digest, epoch FROM spine_bind_card WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            raise SpineBindReplayError("bind row missing")
        if row["digest"] != digest:
            raise SpineBindReplayError("bind replay digest mismatch")
        if int(row["epoch"]) != epoch:
            raise SpineBindReplayError("bind replay epoch mismatch")
        after = self._count(tenant_id)
        if after != before:
            raise SpineBindReplayError("bind replay inserted a row")
        return {
            "kind": "spine_bind_replay",
            "hit": True,
            "law": "bind-replay-does-not-insert",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "digest": digest,
            "epoch_before": epoch,
            "epoch_after": int(row["epoch"]),
            "rows_before": before,
            "rows_after": after,
            "inserted": False,
            "moved": False,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _count(self, tenant_id: str) -> int:
        try:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM spine_bind_card WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindReplayError("bind journal missing") from exc
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
