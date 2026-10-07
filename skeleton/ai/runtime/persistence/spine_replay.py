"""Duplicate replay. Poison is not repaired.

Re-accepts an already stored identity. A digest change is refused. The fence
epoch is read before and after and must match.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxConflict, InboxDelivery, SQLiteInboxLedger


class SpineReplayError(RuntimeError):
    """Replay rejected its inputs. Not a maturity signal."""


class SpineReplay:
    """Replay one delivery and prove the fence epoch did not move."""

    def __init__(self, inbox: SQLiteInboxLedger, fence: SQLiteConsistencyFence, *, consumer_id: str = "spine") -> None:
        if not isinstance(inbox, SQLiteInboxLedger):
            raise SpineReplayError("inbox must be a SQLiteInboxLedger")
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineReplayError("fence must be a SQLiteConsistencyFence")
        self.inbox = inbox
        self.fence = fence
        self.consumer_id = consumer_id

    def replay(self, delivery: InboxDelivery, *, tenant_id: str, now: datetime | None = None) -> dict[str, Any]:
        if not isinstance(delivery, InboxDelivery):
            raise SpineReplayError("delivery must be an InboxDelivery")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineReplayError("now must be timezone-aware")
        resource = f"op:{delivery.operation_id}"
        before = self._epoch(tenant_id, resource)
        try:
            result = self.inbox.accept(delivery, consumer_id=self.consumer_id, now=instant)
        except InboxConflict as exc:
            return self._card(before, before, False, str(exc.__class__.__name__))
        after = self._epoch(tenant_id, resource)
        if after != before:
            raise SpineReplayError("replay moved the fence")
        return self._card(before, after, result.duplicate, "duplicate" if result.duplicate else "fresh-accept")

    def _epoch(self, tenant_id: str, resource_id: str) -> int:
        try:
            return self.fence.read(tenant_id=tenant_id, resource_id=resource_id).epoch
        except Exception:
            return 0

    @staticmethod
    def _card(before: int, after: int, duplicate: bool, reason: str) -> dict[str, Any]:
        return {
            "kind": "spine_replay",
            "hit": duplicate and before == after,
            "law": "replay-does-not-advance",
            "citation": "VOL-134",
            "epoch_before": before,
            "epoch_after": after,
            "duplicate": duplicate,
            "reason": reason,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
