"""Typed in-process event bus for frontier subsystem boundaries."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Mapping


@dataclass(frozen=True, slots=True)
class DomainEvent:
    topic: str
    payload: Mapping[str, object]
    occurred_at: datetime

    @classmethod
    def create(cls, topic: str, payload: Mapping[str, object]) -> "DomainEvent":
        if not topic.strip():
            raise ValueError("topic must not be empty")
        return cls(topic=topic.strip(), payload=dict(payload), occurred_at=datetime.now(timezone.utc))


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """Ordered async fan-out bus; handler failures do not erase delivery state."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, handler: Handler) -> None:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        async with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

    async def publish(self, event: DomainEvent) -> int:
        async with self._lock:
            handlers = tuple(self._handlers.get(event.topic, ()))
        delivered = 0
        for handler in handlers:
            await handler(event)
            delivered += 1
        return delivered
