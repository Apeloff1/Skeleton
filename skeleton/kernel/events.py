"""The Skeleton domain event bus.

A synchronous, in-process pub/sub bus. It is deliberately synchronous: domain
events in Skeleton are facts about things that already happened, and a handler
that needs asynchrony should hand off to the agent scheduler rather than
making the bus itself concurrent. Synchronous dispatch keeps causal ordering
obvious and makes tests deterministic.

Features
--------
- Topics are dotted strings (``pipeline.npc.completed``). Subscribers can
  match exactly or by prefix wildcard (``pipeline.*``, ``*``).
- Every event carries a ``correlation_id`` threading the whole causal chain
  of a pipeline run, and a ``causation_id`` naming the event that caused it.
- The bus retains a bounded replay buffer; late subscribers can catch up.
- A failing handler is isolated: it is logged, wrapped, and never prevents
  other handlers for the same event from running. All handler failures for a
  publish are collected and raised afterwards as an ``EventBusError`` only
  when ``strict=True``.
"""

from __future__ import annotations

import fnmatch
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from skeleton.kernel.errors import EventBusError

logger = logging.getLogger(__name__)

EventHandler = Callable[["DomainEvent"], None]


@dataclass(frozen=True)
class DomainEvent:
    """An immutable fact about something that happened in the system.

    ``payload`` must be JSON-serialisable — events may be persisted or shipped
    to external consumers without transformation.
    """

    topic: str
    payload: dict[str, Any]
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    causation_id: str | None = None
    occurred_at: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def derive(self, topic: str, payload: dict[str, Any]) -> "DomainEvent":
        """Create a follow-on event, threading correlation and causation ids."""
        return DomainEvent(
            topic=topic,
            payload=payload,
            correlation_id=self.correlation_id,
            causation_id=self.event_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class _Subscription:
    pattern: str
    handler: EventHandler
    name: str

    def matches(self, topic: str) -> bool:
        return self.pattern == "*" or fnmatch.fnmatchcase(topic, self.pattern)


class EventBus:
    """Synchronous domain event bus with replay and failure isolation."""

    def __init__(self, *, replay_capacity: int = 1024) -> None:
        self._subscriptions: list[_Subscription] = []
        self._replay: deque[DomainEvent] = deque(maxlen=replay_capacity)
        self._published_count = 0

    # -- subscription ------------------------------------------------------

    def subscribe(
        self,
        pattern: str,
        handler: EventHandler,
        *,
        name: str | None = None,
        replay: bool = False,
    ) -> Callable[[], None]:
        """Subscribe ``handler`` to events matching ``pattern``.

        Returns an unsubscribe callable. With ``replay=True`` the handler is
        immediately fed the retained history that matches the pattern, in
        order, before this call returns.
        """
        if not pattern or not isinstance(pattern, str):
            raise EventBusError("Subscription pattern must be a non-empty string")
        sub = _Subscription(pattern=pattern, handler=handler, name=name or getattr(handler, "__name__", "handler"))
        self._subscriptions.append(sub)
        if replay:
            for event in list(self._replay):
                if sub.matches(event.topic):
                    self._dispatch(sub, event)

        def unsubscribe() -> None:
            try:
                self._subscriptions.remove(sub)
            except ValueError:
                pass

        return unsubscribe

    def subscription_count(self, pattern: str | None = None) -> int:
        if pattern is None:
            return len(self._subscriptions)
        return sum(1 for s in self._subscriptions if s.pattern == pattern)

    # -- publishing ----------------------------------------------------------

    def publish(self, event: DomainEvent, *, strict: bool = False) -> list[Exception]:
        """Publish an event to every matching subscriber.

        Returns the list of handler exceptions (empty when all handlers
        succeeded). With ``strict=True``, raises an ``EventBusError`` wrapping
        the failures after all handlers have been attempted.
        """
        if not isinstance(event, DomainEvent):
            raise EventBusError("publish() requires a DomainEvent")
        self._replay.append(event)
        self._published_count += 1
        failures: list[Exception] = []
        for sub in list(self._subscriptions):
            if sub.matches(event.topic):
                try:
                    sub.handler(event)
                except Exception as exc:  # noqa: BLE001 - isolation is the point
                    logger.exception("Event handler %r failed on topic %r", sub.name, event.topic)
                    failures.append(exc)
        if strict and failures:
            raise EventBusError(
                f"{len(failures)} handler(s) failed for topic {event.topic!r}",
                context={"topic": event.topic, "failures": [repr(f) for f in failures]},
            )
        return failures

    def emit(
        self,
        topic: str,
        payload: dict[str, Any] | None = None,
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        strict: bool = False,
    ) -> DomainEvent:
        """Convenience: build and publish an event in one call."""
        event = DomainEvent(
            topic=topic,
            payload=payload or {},
            correlation_id=correlation_id or uuid.uuid4().hex,
            causation_id=causation_id,
        )
        self.publish(event, strict=strict)
        return event

    # -- introspection -------------------------------------------------------

    def replay(self, pattern: str = "*", *, limit: int | None = None) -> list[DomainEvent]:
        """Return retained events matching ``pattern``, oldest first."""
        matches = [e for e in self._replay if fnmatch.fnmatchcase(e.topic, pattern)]
        return matches[-limit:] if limit is not None else matches

    def trace(self, correlation_id: str) -> list[DomainEvent]:
        """Return the full causal chain for a correlation id, in order."""
        return [e for e in self._replay if e.correlation_id == correlation_id]

    def clear_history(self) -> None:
        self._replay.clear()

    @property
    def published_count(self) -> int:
        return self._published_count

    def stats(self) -> dict[str, Any]:
        return {
            "subscriptions": len(self._subscriptions),
            "published_total": self._published_count,
            "retained": len(self._replay),
            "replay_capacity": self._replay.maxlen,
        }


def topics_under(prefix: str, events: Iterable[DomainEvent]) -> list[str]:
    """Utility: distinct topics under a dotted prefix, from an event iterable."""
    return sorted({e.topic for e in events if e.topic == prefix or e.topic.startswith(prefix + ".")})
