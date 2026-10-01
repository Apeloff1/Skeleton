"""Refuse a bind seal when a hold row exists.

A held outbox id for the same tenant blocks the seal. A foreign hold does
not. The epoch is recorded and must not move. applied stays 0. This reader
does not accept a delivery and does not start a dispatcher.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldError(RuntimeError):
    """Bind hold rejected its inputs. Not a maturity signal."""


class SpineBindHold:
    """Block a seal on a held id. Do not apply."""

    def __init__(self, hold_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(hold_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def refuse(
        self,
        *,
        tenant_id: str,
        outbox_id: str,
        bind: dict[str, Any],
        epoch_before: int,
        epoch_after: int,
    ) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldError("outbox_id must be non-empty text")
        if not isinstance(bind, dict) or bind.get("kind") != "spine_bind_card":
            raise SpineBindHoldError("bind must be a spine_bind_card")
        if bind.get("tenant_id") != tenant_id:
            raise SpineBindHoldError("bind tenant does not match")
        if bind.get("apply_landed") is not False or bind.get("moved") is not False:
            raise SpineBindHoldError("bind card is not dark")
        if not isinstance(epoch_before, int) or not isinstance(epoch_after, int):
            raise SpineBindHoldError("epochs must be ints")
        if epoch_before < 0 or epoch_after < 0 or epoch_before != epoch_after:
            raise SpineBindHoldError("hold read moved the fence")
        try:
            row = self._connection.execute(
                """
                SELECT hold_id, reason FROM spine_hold
                WHERE tenant_id = ? AND outbox_id = ?
                ORDER BY hold_id
                LIMIT 1
                """,
                (tenant_id, outbox_id),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldError("hold journal missing") from exc
        held = row is not None
        return {
            "kind": "spine_bind_hold",
            "hit": False,
            "law": "held-id-refuses-bind",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "held": held,
            "sealed": False,
            "hold_id": None if row is None else int(row["hold_id"]),
            "reason": None if row is None else row["reason"],
            "epoch_before": epoch_before,
            "epoch_after": epoch_after,
            "moved": False,
            "applied": 0,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
