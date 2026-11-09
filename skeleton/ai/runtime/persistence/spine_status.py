"""Status card for the landed P2 spine. Not a completion signal."""

from __future__ import annotations

from typing import Any

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.spine_cursor import SpineCursorRead
from skeleton.persistence.spine_projection import SpineProjection


class SpineStatusError(RuntimeError):
    """Status input cannot be read. Not a maturity signal."""


class SpineStatus:
    """Aggregate cursor, fence, and poison into one card."""

    def __init__(
        self,
        projection: SpineProjection,
        inbox: SQLiteInboxLedger,
        fence: SQLiteConsistencyFence,
    ) -> None:
        if not isinstance(projection, SpineProjection):
            raise SpineStatusError("projection must be a SpineProjection")
        if not isinstance(inbox, SQLiteInboxLedger):
            raise SpineStatusError("inbox must be a SQLiteInboxLedger")
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineStatusError("fence must be a SQLiteConsistencyFence")
        self.projection = projection
        self.inbox = inbox
        self.fence = fence
        self.cursor = SpineCursorRead(projection, fence)

    def card(self, *, tenant_id: str, resource_id: str) -> dict[str, Any]:
        cursor = self.cursor.read(tenant_id=tenant_id, resource_id=resource_id)
        return {
            "kind": "spine_status",
            "hit": cursor.poison_count == 0,
            "law": "spine-status-read",
            "citation": "VOL-134",
            "applied_count": cursor.applied_count,
            "poison_count": cursor.poison_count,
            "fence_epoch": cursor.fence_epoch,
            "inbox": self.inbox.card()["kind"] if hasattr(self.inbox, "card") else "inbox",
            "fence": self.fence.card()["kind"],
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
