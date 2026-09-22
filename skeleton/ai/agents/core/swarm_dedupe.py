"""Bounded, thread-safe result deduplication for at-least-once swarm execution."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class Completion:
    task_id: str
    token: str
    recorded_at: float


class CompletionCache:
    def __init__(
        self,
        *,
        max_entries: int = 100_000,
        ttl_seconds: float = 3_600,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("invalid completion cache configuration")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._items: OrderedDict[tuple[str, str], Completion] = OrderedDict()
        self._lock = RLock()

    def _purge_locked(self) -> int:
        cutoff = self.clock() - self.ttl_seconds
        removed = 0
        expired = [key for key, item in self._items.items() if item.recorded_at <= cutoff]
        for key in expired:
            self._items.pop(key, None)
            removed += 1
        return removed

    def record(self, task_id: str, token: str) -> bool:
        task_id = task_id.strip()
        token = token.strip()
        if not task_id or not token:
            raise ValueError("task_id and completion token must not be empty")
        with self._lock:
            self._purge_locked()
            key = (task_id, token)
            if key in self._items:
                self._items.move_to_end(key)
                return False
            self._items[key] = Completion(task_id, token, self.clock())
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
            return True

    def forget(self, task_id: str, token: str) -> bool:
        with self._lock:
            return self._items.pop((task_id.strip(), token.strip()), None) is not None

    def contains(self, task_id: str, token: str) -> bool:
        with self._lock:
            self._purge_locked()
            return (task_id.strip(), token.strip()) in self._items

    def purge(self) -> int:
        with self._lock:
            return self._purge_locked()

    def snapshot(self) -> tuple[Completion, ...]:
        with self._lock:
            self._purge_locked()
            return tuple(self._items.values())

    def __len__(self) -> int:
        with self._lock:
            self._purge_locked()
            return len(self._items)
