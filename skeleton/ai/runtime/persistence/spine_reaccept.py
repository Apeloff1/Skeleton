"""Digest-stable reaccept.

Accepts only when the caller digest matches the delivery digest. A mismatch
is refused before accept. A duplicate does not move the fence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import InboxConflict, InboxDelivery, SQLiteInboxLedger


class SpineReacceptError(RuntimeError):
    """Reaccept rejected its inputs. Not a maturity signal."""


class SpineReaccept:
    """Reaccept one delivery only when the digest matches."""

    def __init__(self, inbox: SQLiteInboxLedger, fence: SQLiteConsistencyFence, *, consumer_id: str = "spine") -> None:
        if not isinstance(inbox, SQLiteInboxLedger):
            raise SpineReacceptError("inbox must be a SQLiteInboxLedger")
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineReacceptError("fence must be a SQLiteConsistencyFence")
        self.inbox = inbox
        self.fence = fence
        self.consumer_id = consumer_id

    def reaccept(
        self,
        delivery: InboxDelivery,
        *,
        tenant_id: str,
        expected_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(delivery, InboxDelivery):
            raise SpineReacceptError("delivery must be an InboxDelivery")
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise SpineReacceptError("expected_digest must be SHA-256 hex")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineReacceptError("now must be timezone-aware")
        resource = f"op:{delivery.operation_id}"
        before = self._epoch(tenant_id, resource)
        if delivery.digest() != expected_digest:
            return self._card(before, before, False, "digest-mismatch")
        try:
            result = self.inbox.accept(delivery, consumer_id=self.consumer_id, now=instant)
        except InboxConflict:
            return self._card(before, self._epoch(tenant_id, resource), False, "InboxConflict")
        after = self._epoch(tenant_id, resource)
        return self._card(before, after, result.duplicate, "duplicate" if result.duplicate else "accepted")

    def _epoch(self, tenant_id: str, resource_id: str) -> int:
        try:
            return self.fence.read(tenant_id=tenant_id, resource_id=resource_id).epoch
        except Exception:
            return 0

    @staticmethod
    def _card(before: int, after: int, duplicate: bool, reason: str) -> dict[str, Any]:
        return {
            "kind": "spine_reaccept",
            "hit": reason != "digest-mismatch" and before == after,
            "law": "digest-stable-reaccept",
            "citation": "VOL-134",
            "epoch_before": before,
            "epoch_after": after,
            "duplicate": duplicate,
            "reason": reason,
            "applied_fence": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
