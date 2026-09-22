"""Fenced human-review claims for multi-instance AI shell services."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import FencedLease, LeaseConflict
from skeleton.shells.ai.review import AIReviewView
from skeleton.shells.ai.review_queue import ReviewQueueConflict, ReviewState
from skeleton.shells.ai.store_protocol import DistributedAIBackend


@dataclass(frozen=True)
class DistributedReviewRecord:
    item_id: str
    review: AIReviewView
    state: ReviewState
    reviewer: str = ""
    reason: str = ""
    expires_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "state": self.state.value,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "review": self.review.to_dict(),
        }


@dataclass(frozen=True)
class DistributedReviewClaim:
    item_id: str
    reviewer: str
    lease: FencedLease

    @property
    def fencing_token(self) -> int:
        return self.lease.fencing_token


class DistributedAIReviewQueue:
    """Review decisions are fenced writes under a short claim lease."""

    def __init__(
        self,
        backend: DistributedAIBackend,
        *,
        namespace: str = "shell-ai-review",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.backend = backend
        self.namespace = namespace
        self._clock = clock

    def enqueue(
        self,
        review: AIReviewView,
        *,
        ttl_seconds: float = 900.0,
    ) -> DistributedReviewRecord:
        if ttl_seconds <= 0:
            raise ValueError("review TTL must be positive")
        now = self._clock()
        nonce = secrets.token_hex(16)
        raw = f"{review.proposal_fingerprint}:{now}:{nonce}".encode()
        item_id = hashlib.sha256(raw).hexdigest()[:32]
        record = DistributedReviewRecord(
            item_id,
            review,
            ReviewState.PENDING,
            expires_at=now + ttl_seconds,
        )
        try:
            self.backend.put_if_absent(self.namespace, item_id, record)
        except Exception as exc:
            raise ReviewQueueConflict("distributed review enqueue conflict") from exc
        return record

    def get(self, item_id: str) -> DistributedReviewRecord:
        current = self.backend.get(self.namespace, item_id)
        if current is None or not isinstance(current.value, DistributedReviewRecord):
            raise KeyError(item_id)
        item = current.value
        if item.state in {ReviewState.PENDING, ReviewState.CLAIMED} and item.expires_at <= self._clock():
            expired = DistributedReviewRecord(
                item.item_id,
                item.review,
                ReviewState.EXPIRED,
                item.reviewer,
                item.reason,
                item.expires_at,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    item_id,
                    expected_revision=current.revision,
                    value=expired,
                )
                return expired
            except Exception:
                latest = self.backend.get(self.namespace, item_id)
                if latest is not None and isinstance(latest.value, DistributedReviewRecord):
                    return latest.value
        return item

    def claim(
        self,
        item_id: str,
        reviewer: str,
        *,
        ttl_seconds: float = 120.0,
    ) -> DistributedReviewClaim:
        item = self.get(item_id)
        if item.state is not ReviewState.PENDING:
            raise ReviewQueueConflict("distributed review item is not pending")
        try:
            lease = self.backend.acquire_lease(
                self.namespace,
                item_id,
                owner=reviewer,
                ttl_seconds=ttl_seconds,
            )
        except LeaseConflict as exc:
            raise ReviewQueueConflict("distributed review already claimed") from exc
        current = self.backend.get(self.namespace, item_id)
        if current is None or not isinstance(current.value, DistributedReviewRecord):
            self.backend.release_lease(lease)
            raise ReviewQueueConflict("distributed review disappeared")
        claimed = DistributedReviewRecord(
            item.item_id,
            item.review,
            ReviewState.CLAIMED,
            reviewer,
            "",
            item.expires_at,
        )
        try:
            self.backend.fenced_compare_and_swap(
                lease,
                expected_revision=current.revision,
                value=claimed,
            )
        except Exception:
            self.backend.release_lease(lease)
            raise
        return DistributedReviewClaim(item_id, reviewer, lease)

    def decide(
        self,
        claim: DistributedReviewClaim,
        *,
        approve: bool,
        reason: str = "",
    ) -> DistributedReviewRecord:
        if len(reason) > 1024:
            raise ValueError("review decision reason too long")
        self.backend.require_fence(claim.lease)
        current = self.backend.get(self.namespace, claim.item_id)
        if current is None or not isinstance(current.value, DistributedReviewRecord):
            raise ReviewQueueConflict("distributed review item missing")
        if current.value.state is not ReviewState.CLAIMED:
            raise ReviewQueueConflict("distributed review is not claimed")
        if current.value.reviewer != claim.reviewer:
            raise ReviewQueueConflict("distributed review reviewer mismatch")
        decided = DistributedReviewRecord(
            current.value.item_id,
            current.value.review,
            ReviewState.APPROVED if approve else ReviewState.REJECTED,
            claim.reviewer,
            reason,
            current.value.expires_at,
        )
        try:
            updated = self.backend.fenced_compare_and_swap(
                claim.lease,
                expected_revision=current.revision,
                value=decided,
            )
        finally:
            try:
                self.backend.release_lease(claim.lease)
            except LeaseConflict:
                pass
        if not isinstance(updated.value, DistributedReviewRecord):
            raise RuntimeError("distributed review backend returned invalid value")
        return updated.value
