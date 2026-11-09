"""Bounded event publication contract distilled from gameforge-rs.

Source: Apeloff1/gameforge-rs, gf-core event infrastructure.
This module deliberately exposes no framework, database, or vendor dependency.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class EventEnvelope(Generic[T]):
    sequence: int
    value: T


class BoundedEventBus(Generic[T]):
    """FIFO event log with a hard retention bound and monotonic sequence IDs."""

    def __init__(self, capacity: int = 1024) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._events: deque[EventEnvelope[T]] = deque(maxlen=capacity)
        self._capacity = capacity
        self._next_sequence = 0
        self._lock = Lock()

    def publish(self, value: T) -> EventEnvelope[T]:
        with self._lock:
            event = EventEnvelope(self._next_sequence, value)
            self._next_sequence += 1
            self._events.append(event)
            return event

    def since(self, sequence: int) -> tuple[EventEnvelope[T], ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence >= sequence)

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
