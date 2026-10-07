"""Bounded reconciliation queue primitives.

Keeps retry reconciliation state separate from execution handlers and transports.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque


@dataclass(frozen=True)
class ReconciliationItem:
    execution_id: str
    reason: str
    attempt: int


class ReconciliationQueue:
    """Small bounded in-memory queue for retry reconciliation decisions."""

    def __init__(self, max_items: int = 1024) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self._items: Deque[ReconciliationItem] = deque(maxlen=max_items)

    def enqueue(self, item: ReconciliationItem) -> None:
        self._items.append(item)

    def dequeue(self) -> ReconciliationItem | None:
        if not self._items:
            return None
        return self._items.popleft()

    def size(self) -> int:
        return len(self._items)
