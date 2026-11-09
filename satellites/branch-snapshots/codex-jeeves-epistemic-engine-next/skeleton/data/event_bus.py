"""Event bus — pub/sub backbone for cross-subsystem messaging.

Topic-based pub/sub with wildcard subscriptions, per-subscriber
delivery queues, backpressure via bounded buffers, and optional
persistent replay from the event store. All Skeleton subsystems
communicate through the bus; direct imports between subsystems are
reserved for card aggregation only.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Message:
    topic: str
    payload: Dict[str, Any]
    message_id: str = ""
    timestamp_ns: int = 0

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = uuid.uuid4().hex[:12]
        if not self.timestamp_ns:
            self.timestamp_ns = time.time_ns()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "message_id": self.message_id,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass
class Subscriber:
    pattern: str
    handler: Callable[[Message], None]
    queue: List[Message] = field(default_factory=list)
    dropped: int = 0

    def matches(self, topic: str) -> bool:
        if self.pattern == "*":
            return True
        if self.pattern.endswith(".*"):
            return topic.startswith(self.pattern[:-1])
        return topic == self.pattern


class EventBus:
    """Topic pub/sub with wildcards and bounded subscriber queues."""

    def __init__(self, queue_capacity: int = 500):
        self._subs: List[Subscriber] = []
        self._published = 0
        self._delivered = 0
        self.queue_capacity = queue_capacity
        self._replay_log: List[Message] = []

    def subscribe(self, pattern: str, handler: Callable[[Message], None]) -> Subscriber:
        sub = Subscriber(pattern=pattern, handler=handler)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> bool:
        if sub in self._subs:
            self._subs.remove(sub)
            return True
        return False

    def publish(self, topic: str, payload: Dict[str, Any]) -> Message:
        msg = Message(topic=topic, payload=payload)
        self._published += 1
        self._replay_log.append(msg)
        if len(self._replay_log) > 10_000:
            self._replay_log.pop(0)
        for sub in self._subs:
            if not sub.matches(topic):
                continue
            if len(sub.queue) >= self.queue_capacity:
                sub.dropped += 1
                continue
            sub.queue.append(msg)
        return msg

    def drain(self, sub: Subscriber, limit: Optional[int] = None) -> int:
        count = 0
        while sub.queue and (limit is None or count < limit):
            msg = sub.queue.pop(0)
            try:
                sub.handler(msg)
                self._delivered += 1
            except Exception:  # noqa: BLE001
                sub.dropped += 1
            count += 1
        return count

    def drain_all(self) -> int:
        return sum(self.drain(s) for s in self._subs)

    def replay(self, pattern: str, since_ns: int = 0) -> int:
        sub = Subscriber(pattern=pattern, handler=lambda m: None)
        count = 0
        for msg in self._replay_log:
            if msg.timestamp_ns >= since_ns and sub.matches(msg.topic):
                for s in self._subs:
                    if s.matches(msg.topic) and len(s.queue) < self.queue_capacity:
                        s.queue.append(msg)
                count += 1
        return count

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "event-bus-card",
            "subscribers": len(self._subs),
            "published": self._published,
            "delivered": self._delivered,
            "queued": sum(len(s.queue) for s in self._subs),
            "dropped": sum(s.dropped for s in self._subs),
            "replay_log": len(self._replay_log),
        }
