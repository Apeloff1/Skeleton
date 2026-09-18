"""Deterministic bounded queue for shell work admission.

This is intentionally a data structure, not a background worker.  Callers claim
work explicitly, making ownership and scheduling visible to the surrounding
Jeeves/control-plane code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import heapq
import threading
import time
from typing import Callable
import uuid

from skeleton.shells.runner import ShellCommand


class QueueState(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    command: ShellCommand
    priority: int
    created_at: float
    sequence: int
    state: QueueState = QueueState.QUEUED
    owner: str | None = None
    claim_id: str | None = None
    updated_at: float = 0.0


class ShellWorkQueue:
    def __init__(self, *, max_items: int = 4096, clock: Callable[[], float] = time.monotonic) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._clock = clock
        self._items: dict[str, QueueItem] = {}
        self._heap: list[tuple[int, int, str]] = []
        self._sequence = 0
        self._lock = threading.RLock()

    def enqueue(self, command: ShellCommand, *, priority: int = 100, item_id: str | None = None) -> QueueItem:
        with self._lock:
            active = sum(1 for item in self._items.values() if item.state in {QueueState.QUEUED, QueueState.CLAIMED})
            if active >= self.max_items:
                raise RuntimeError("shell work queue capacity exhausted")
            identifier = item_id or uuid.uuid4().hex
            if identifier in self._items:
                raise ValueError("queue item_id already exists")
            self._sequence += 1
            now = self._clock()
            item = QueueItem(identifier, command, priority, now, self._sequence, updated_at=now)
            self._items[identifier] = item
            heapq.heappush(self._heap, (priority, self._sequence, identifier))
            return item

    def claim(self, owner: str) -> QueueItem | None:
        if not owner:
            raise ValueError("queue owner is required")
        with self._lock:
            while self._heap:
                _, _, item_id = heapq.heappop(self._heap)
                item = self._items.get(item_id)
                if item is None or item.state is not QueueState.QUEUED:
                    continue
                now = self._clock()
                claimed = QueueItem(
                    item.item_id,
                    item.command,
                    item.priority,
                    item.created_at,
                    item.sequence,
                    state=QueueState.CLAIMED,
                    owner=owner,
                    claim_id=uuid.uuid4().hex,
                    updated_at=now,
                )
                self._items[item_id] = claimed
                return claimed
            return None

    def _transition(self, item: QueueItem, state: QueueState) -> QueueItem:
        with self._lock:
            current = self._items.get(item.item_id)
            if current is None or current.claim_id != item.claim_id or current.state is not QueueState.CLAIMED:
                raise RuntimeError("queue item claim is stale")
            now = self._clock()
            updated = QueueItem(
                current.item_id,
                current.command,
                current.priority,
                current.created_at,
                current.sequence,
                state=state,
                owner=current.owner,
                claim_id=current.claim_id,
                updated_at=now,
            )
            self._items[item.item_id] = updated
            return updated

    def complete(self, item: QueueItem) -> QueueItem:
        return self._transition(item, QueueState.COMPLETED)

    def fail(self, item: QueueItem) -> QueueItem:
        return self._transition(item, QueueState.FAILED)

    def requeue(self, item: QueueItem, *, priority: int | None = None) -> QueueItem:
        """Return a currently claimed item to the runnable queue.

        The claim token must still be current.  Requeueing clears ownership and
        issues a fresh sequence number so stale claim objects cannot mutate the
        item after it becomes runnable again.
        """
        with self._lock:
            current = self._items.get(item.item_id)
            if current is None or current.claim_id != item.claim_id or current.state is not QueueState.CLAIMED:
                raise RuntimeError("queue item claim is stale")
            self._sequence += 1
            now = self._clock()
            updated = QueueItem(
                current.item_id,
                current.command,
                current.priority if priority is None else priority,
                current.created_at,
                self._sequence,
                state=QueueState.QUEUED,
                owner=None,
                claim_id=None,
                updated_at=now,
            )
            self._items[item.item_id] = updated
            heapq.heappush(self._heap, (updated.priority, updated.sequence, updated.item_id))
            return updated

    def release_claim(self, item: QueueItem, *, priority: int | None = None) -> QueueItem:
        """Compatibility alias for :meth:`requeue` used by worker code."""
        return self.requeue(item, priority=priority)

    def cancel(self, item_id: str) -> QueueItem:
        with self._lock:
            current = self._items[item_id]
            if current.state is not QueueState.QUEUED:
                raise RuntimeError("only queued work may be cancelled")
            updated = QueueItem(
                current.item_id,
                current.command,
                current.priority,
                current.created_at,
                current.sequence,
                state=QueueState.CANCELLED,
                updated_at=self._clock(),
            )
            self._items[item_id] = updated
            return updated

    def get(self, item_id: str) -> QueueItem:
        return self._items[item_id]

    def counts(self) -> dict[str, int]:
        with self._lock:
            return {state.value: sum(1 for item in self._items.values() if item.state is state) for state in QueueState}

    def snapshot(self) -> tuple[QueueItem, ...]:
        with self._lock:
            return tuple(sorted(self._items.values(), key=lambda item: item.sequence))
