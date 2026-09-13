"""Correlated events with ordered, isolated subscriber delivery."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

from skeleton.frontier.execution import positive_int
from skeleton.frontier.payloads import json_snapshot


def _topic(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("topic must contain 1 to 128 characters")
    return value.strip()


@dataclass(frozen=True, slots=True)
class DomainEvent:
    topic: str
    payload: Mapping[str, object]
    occurred_at: datetime
    event_id: str = field(default_factory=lambda: uuid4().hex)
    correlation_id: str | None = None
    causation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "topic", _topic(self.topic))
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        for name in ("event_id", "correlation_id", "causation_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 128):
                raise ValueError(f"{name} must contain 1 to 128 characters")
        if self.event_id is None:
            raise ValueError("event_id is required")
        object.__setattr__(self, "payload", MappingProxyType(json_snapshot(dict(self.payload))))

    @classmethod
    def create(
        cls,
        topic: str,
        payload: Mapping[str, object],
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> DomainEvent:
        return cls(
            topic, payload, datetime.now(UTC), correlation_id=correlation_id, causation_id=causation_id
        )


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    def __init__(self, *, max_subscriptions: int = 1024) -> None:
        self.max_subscriptions = positive_int("max_subscriptions", max_subscriptions)
        self._handlers: dict[str, list[Handler]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, handler: Handler) -> None:
        topic = _topic(topic)
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("event handlers must be async functions")
        async with self._lock:
            if handler in self._handlers.get(topic, ()):
                return
            if sum(map(len, self._handlers.values())) >= self.max_subscriptions:
                raise OverflowError("event subscription capacity reached")
            self._handlers.setdefault(topic, []).append(handler)

    async def unsubscribe(self, topic: str, handler: Handler) -> bool:
        topic = _topic(topic)
        async with self._lock:
            handlers = self._handlers.get(topic, [])
            if handler not in handlers:
                return False
            handlers.remove(handler)
            if not handlers:
                self._handlers.pop(topic, None)
            return True

    async def publish(self, event: DomainEvent) -> int:
        async with self._lock:
            handlers = tuple(self._handlers.get(event.topic, ()))
        payload = json_snapshot(dict(event.payload))
        errors = []
        for handler in handlers:
            try:
                # Every subscriber sees the same input snapshot, even if a
                # previous subscriber mutated a nested list before failing.
                await handler(replace(event, payload=payload))
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("event delivery failed", errors)
        return len(handlers)
