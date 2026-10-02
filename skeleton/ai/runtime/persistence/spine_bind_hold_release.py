"""Prove a bind refusal did not release the hold.

Reads the active hold row after a refusal card. A missing active row or a
released flag fails closed. The proof does not update the hold table and
does not accept a delivery.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_hold import _active_spine_hold, _ensure_spine_hold_schema


class SpineBindHoldReleaseError(RuntimeError):
    """Release proof rejected its inputs. Not a maturity signal."""


class SpineBindHoldRelease:
    """Show the hold is still active. Do not release it."""

    def __init__(self, hold_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(hold_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        _ensure_spine_hold_schema(self._connection)

    def prove(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_hold":
            raise SpineBindHoldReleaseError("card must be a spine_bind_hold")
        if card.get("held") is not True or card.get("sealed") is not False:
            raise SpineBindHoldReleaseError("refusal is not a hold")
        if card.get("applied") != 0 or card.get("moved") is not False:
            raise SpineBindHoldReleaseError("refusal is not dark")
        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldReleaseError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldReleaseError("outbox_id must be non-empty text")
        epoch = card.get("epoch_before")
        if not isinstance(epoch, int) or epoch < 0 or epoch != card.get("epoch_after"):
            raise SpineBindHoldReleaseError("refusal epoch moved")
        row = _active_spine_hold(self._connection, tenant_id=tenant_id, outbox_id=outbox_id)
        if row is None:
            raise SpineBindHoldReleaseError("refusal released the hold")
        if card.get("hold_id") != int(row["hold_id"]):
            raise SpineBindHoldReleaseError("refusal hold id mismatch")
        return {
            "kind": "spine_bind_hold_release",
            "hit": False,
            "law": "refusal-does-not-release-hold",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "hold_id": int(row["hold_id"]),
            "released": False,
            "applied": 0,
            "sealed": False,
            "epoch_before": epoch,
            "epoch_after": epoch,
            "moved": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
