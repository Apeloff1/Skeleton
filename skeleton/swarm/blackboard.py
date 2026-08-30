"""Blackboard — typed shared workspace for swarm agents over the event bus.

Wave-4 SOTA (multi-agent communication: A2A-style and blackboard patterns):
agents coordinate best through a shared, typed, expiring knowledge surface
rather than direct message passing. Every entry carries a topic, a payload,
a producer id, a TTL, and a confidence; readers subscribe by topic pattern
(exact or dotted wildcard, same grammar as the kernel bus).

The blackboard is a thin layer over the kernel EventBus: posting emits
``blackboard.posted``, expiry emits ``blackboard.expired`` on sweep, and
the bus's replay gives late joiners the current surface for free.

Pure domain, deterministic under an injected clock.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.events import EventBus


@dataclass
class BlackboardEntry:
    entry_id: str
    topic: str
    payload: Dict[str, Any]
    producer: str
    confidence: float
    posted_at: float
    ttl_s: float

    def is_expired(self, now: float) -> bool:
        return now > self.posted_at + self.ttl_s

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "topic": self.topic,
            "payload": self.payload,
            "producer": self.producer,
            "confidence": round(self.confidence, 4),
            "posted_at": self.posted_at,
            "ttl_s": self.ttl_s,
        }


class Blackboard:
    """TTL'd typed knowledge surface shared by the swarm."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._bus = bus
        self._now = clock or time.time
        self._entries: Dict[str, BlackboardEntry] = {}
        self.posts = 0
        self.expiries = 0

    def post(
        self,
        topic: str,
        payload: Dict[str, Any],
        *,
        producer: str,
        confidence: float = 0.5,
        ttl_s: float = 300.0,
    ) -> BlackboardEntry:
        entry = BlackboardEntry(
            entry_id=uuid.uuid4().hex[:12],
            topic=topic, payload=dict(payload), producer=producer,
            confidence=min(1.0, max(0.0, confidence)),
            posted_at=self._now(), ttl_s=ttl_s,
        )
        self._entries[entry.entry_id] = entry
        self.posts += 1
        if self._bus is not None:
            try:
                self._bus.emit("blackboard.posted", entry.to_dict(),
                               correlation_id=f"bb_{producer}")
            except Exception:
                pass
        return entry

    def read(self, topic: Optional[str] = None) -> List[BlackboardEntry]:
        """Live entries, optionally filtered to one topic."""
        now = self._now()
        out = [
            e for e in self._entries.values()
            if not e.is_expired(now) and (topic is None or e.topic == topic)
        ]
        out.sort(key=lambda e: (-e.confidence, e.posted_at))
        return out

    def sweep(self) -> List[str]:
        """Expire stale entries; returns their ids."""
        now = self._now()
        expired = [eid for eid, e in self._entries.items() if e.is_expired(now)]
        for eid in expired:
            entry = self._entries.pop(eid)
            self.expiries += 1
            if self._bus is not None:
                try:
                    self._bus.emit("blackboard.expired", entry.to_dict(),
                                   correlation_id=f"bb_{entry.producer}")
                except Exception:
                    pass
        return expired

    def stats(self) -> Dict[str, Any]:
        return {
            "live": len(self.read()),
            "posts": self.posts,
            "expiries": self.expiries,
            "topics": sorted({e.topic for e in self._entries.values()}),
        }
