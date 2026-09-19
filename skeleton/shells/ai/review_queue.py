"""Claim-token queue for human review of AI shell plans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.ai.review import AIReviewView


class ReviewState(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ReviewQueueItem:
    item_id: str
    review: AIReviewView
    state: ReviewState
    created_at: float
    expires_at: float
    claim_id: str = ""
    reviewer: str = ""
    decision_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "claim_id": self.claim_id,
            "reviewer": self.reviewer,
            "decision_reason": self.decision_reason,
            "review": self.review.to_dict(),
        }


class ReviewQueueConflict(RuntimeError):
    pass


class AIReviewQueue:
    def __init__(
        self,
        *,
        max_items: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._clock = clock
        self._serial = 0
        self._items: dict[str, ReviewQueueItem] = {}
        self._lock = threading.RLock()

    def enqueue(self, review: AIReviewView, *, ttl_seconds: float = 900.0) -> ReviewQueueItem:
        if ttl_seconds <= 0:
            raise ValueError("review TTL must be positive")
        with self._lock:
            if len(self._items) >= self.max_items:
                raise RuntimeError("AI review queue capacity exhausted")
            self._serial += 1
            now = self._clock()
            raw = f"{review.proposal_fingerprint}:{self._serial}:{now}"
            item_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
            item = ReviewQueueItem(
                item_id,
                review,
                ReviewState.PENDING,
                now,
                now + ttl_seconds,
            )
            self._items[item_id] = item
            return item

    def _current(self, item_id: str) -> ReviewQueueItem:
        item = self._items[item_id]
        if item.expires_at <= self._clock() and item.state in {
            ReviewState.PENDING,
            ReviewState.CLAIMED,
        }:
            item = ReviewQueueItem(
                item.item_id,
                item.review,
                ReviewState.EXPIRED,
                item.created_at,
                item.expires_at,
                item.claim_id,
                item.reviewer,
                item.decision_reason,
            )
            self._items[item_id] = item
        return item

    def claim(self, item_id: str, reviewer: str) -> ReviewQueueItem:
        if not reviewer or len(reviewer) > 256:
            raise ValueError("invalid reviewer")
        with self._lock:
            item = self._current(item_id)
            if item.state is not ReviewState.PENDING:
                raise ReviewQueueConflict("review item is not pending")
            raw = f"{item_id}:{reviewer}:{self._clock()}"
            claim_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
            updated = ReviewQueueItem(
                item.item_id,
                item.review,
                ReviewState.CLAIMED,
                item.created_at,
                item.expires_at,
                claim_id,
                reviewer,
            )
            self._items[item_id] = updated
            return updated

    def decide(
        self,
        item_id: str,
        *,
        claim_id: str,
        approve: bool,
        reason: str = "",
    ) -> ReviewQueueItem:
        if len(reason) > 1024:
            raise ValueError("review decision reason too long")
        with self._lock:
            item = self._current(item_id)
            if item.state is not ReviewState.CLAIMED:
                raise ReviewQueueConflict("review item is not claimed")
            if item.claim_id != claim_id:
                raise ReviewQueueConflict("stale or foreign review claim")
            updated = ReviewQueueItem(
                item.item_id,
                item.review,
                ReviewState.APPROVED if approve else ReviewState.REJECTED,
                item.created_at,
                item.expires_at,
                item.claim_id,
                item.reviewer,
                reason,
            )
            self._items[item_id] = updated
            return updated

    def get(self, item_id: str) -> ReviewQueueItem:
        with self._lock:
            return self._current(item_id)

    def snapshot(self) -> tuple[ReviewQueueItem, ...]:
        with self._lock:
            return tuple(self._current(key) for key in sorted(self._items))
