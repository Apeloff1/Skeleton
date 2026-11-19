"""Bounded detached event history with explicit consumer gap detection."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import json
from threading import RLock
from typing import Generic, TypeVar

from skeleton.frontier.payloads import json_snapshot

T = TypeVar("T")


class EventHistoryGap(RuntimeError):
    """The requested history was evicted; recover from a trusted checkpoint."""


@dataclass(frozen=True)
class EventEnvelope(Generic[T]):
    sequence: int
    value: T


@dataclass(frozen=True)
class EventBatch(Generic[T]):
    earliest: int
    next_sequence: int
    events: tuple[EventEnvelope[T], ...]


class BoundedEventBus(Generic[T]):
    """Local JSON event history, not persistent delivery authority."""

    def __init__(self, capacity: int = 1024, *, max_bytes: int = 8 << 20,
                 max_event_bytes: int = 256 << 10) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 65_536:
            raise ValueError("invalid event capacity")
        if (type(max_bytes) is not int or not 1 <= max_bytes <= 64 << 20
                or type(max_event_bytes) is not int
                or not 1 <= max_event_bytes <= min(max_bytes, 8 << 20)):
            raise ValueError("invalid event byte budget")
        self._events = deque()
        self._capacity = capacity
        self._max_bytes = max_bytes
        self._max_event_bytes = max_event_bytes
        self._bytes = 0
        self._next_sequence = 0
        self._lock = RLock()

    def publish(self, value: T) -> EventEnvelope[T]:
        value = json_snapshot(value, max_bytes=self._max_event_bytes)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("ascii")
        with self._lock:
            if self._next_sequence >= (1 << 63) - 1:
                raise RuntimeError("event sequence exhausted")
            while self._events and (len(self._events) >= self._capacity
                                    or self._bytes + len(raw) > self._max_bytes):
                self._bytes -= len(self._events.popleft()[1])
            seq = self._next_sequence
            self._next_sequence += 1
            self._events.append((seq, raw))
            self._bytes += len(raw)
            return EventEnvelope(seq, json.loads(raw))

    def read(self, sequence: int, *, limit: int = 1024,
             require_contiguous: bool = True) -> EventBatch[T]:
        if type(sequence) is not int or not 0 <= sequence < 1 << 63:
            raise ValueError("invalid event sequence")
        if type(limit) is not int or not 1 <= limit <= 65_536:
            raise ValueError("invalid event batch limit")
        if type(require_contiguous) is not bool:
            raise ValueError("explicit history policy required")
        with self._lock:
            earliest = self._events[0][0] if self._events else self._next_sequence
            if require_contiguous and not earliest <= sequence <= self._next_sequence:
                raise EventHistoryGap("event cursor outside retained history")
            rows = []
            for seq, raw in self._events:
                if seq >= sequence:
                    rows.append(EventEnvelope(seq, json.loads(raw)))
                    if len(rows) >= limit:
                        break
            return EventBatch(earliest, self._next_sequence, tuple(rows))

    def since(self, sequence: int) -> tuple[EventEnvelope[T], ...]:
        """Compatibility view; authoritative consumers must use read()."""
        return self.read(sequence, limit=self._capacity,
                         require_contiguous=False).events

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
