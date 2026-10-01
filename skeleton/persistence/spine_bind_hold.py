"""Refuse a bind seal while the exact tenant/outbox has an active hold.

Released hold rows remain audit evidence but do not block a later bind. The
reader never accepts a delivery, advances a fence, or starts a dispatcher.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_hold import (
    _active_spine_hold,
    _ensure_spine_hold_schema,
)


class SpineBindHoldError(RuntimeError):
    """Bind hold rejected its inputs. Not a maturity signal."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpineBindHold:
    """Block a seal on the latest active held id. Do not apply."""

    def __init__(self, hold_path: str | Path) -> None:
        self._connection = sqlite3.connect(
            str(hold_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        table = self._connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'spine_hold'
            """
        ).fetchone()
        self._schema_ready = table is not None
        if self._schema_ready:
            _ensure_spine_hold_schema(self._connection)

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
        bind_digest = bind.get("digest")
        if (
            not isinstance(bind_digest, str)
            or _DIGEST_RE.fullmatch(bind_digest) is None
        ):
            raise SpineBindHoldError(
                "bind digest must be lowercase SHA-256 hex"
            )
        if (
            isinstance(epoch_before, bool)
            or not isinstance(epoch_before, int)
            or isinstance(epoch_after, bool)
            or not isinstance(epoch_after, int)
        ):
            raise SpineBindHoldError("epochs must be ints")
        if epoch_before < 0 or epoch_after < 0 or epoch_before != epoch_after:
            raise SpineBindHoldError("hold read moved the fence")
        if not self._schema_ready:
            raise SpineBindHoldError("hold journal missing")

        try:
            row = _active_spine_hold(
                self._connection,
                tenant_id=tenant_id,
                outbox_id=outbox_id,
            )
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
            "bind_digest": bind_digest,
            "held": held,
            "sealed": False,
            "hold_id": None if row is None else int(row["hold_id"]),
            "reason": None if row is None else str(row["reason"]),
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
