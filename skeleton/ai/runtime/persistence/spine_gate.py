"""Hold gate in front of reaccept.

A held outbox id is refused. An unheld id is passed to digest-stable reaccept.
The gate does not advance a fence.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from skeleton.persistence.inbox_ledger import InboxDelivery
from skeleton.persistence.spine_hold import (
    _active_spine_hold,
    _ensure_spine_hold_schema,
)
from skeleton.persistence.spine_reaccept import SpineReaccept


class SpineGateError(RuntimeError):
    """Gate rejected its inputs. Not a maturity signal."""


class SpineGate:
    """Refuse a held outbox id. Otherwise reaccept."""

    def __init__(self, hold_path: str | Path, reaccept: SpineReaccept) -> None:
        if not isinstance(reaccept, SpineReaccept):
            raise SpineGateError("reaccept must be a SpineReaccept")
        self.reaccept = reaccept
        self._connection = sqlite3.connect(str(hold_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        _ensure_spine_hold_schema(self._connection)

    def allow(
        self,
        delivery: InboxDelivery,
        *,
        tenant_id: str,
        expected_digest: str,
        outbox_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = _active_spine_hold(
            self._connection,
            tenant_id=tenant_id,
            outbox_id=outbox_id,
        )
        if row is not None:
            return {
                "kind": "spine_gate",
                "hit": False,
                "law": "held-id-refused",
                "citation": "VOL-134",
                "reason": "held",
                "applied_fence": False,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }
        card = self.reaccept.reaccept(
            delivery,
            tenant_id=tenant_id,
            expected_digest=expected_digest,
            now=now,
        )
        card["kind"] = "spine_gate"
        return card

    def close(self) -> None:
        self._connection.close()
