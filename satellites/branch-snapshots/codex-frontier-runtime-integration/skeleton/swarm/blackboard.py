"""Blackboard — typed shared workspace for swarm agents over the event bus.

Wave-4 SOTA (multi-agent communication: A2A-style and blackboard patterns):
agents coordinate best through a shared, typed, expiring knowledge surface
rather than direct message passing. Every entry carries a topic, a payload,
a producer id, a TTL, and a confidence; readers subscribe by topic pattern
(exact or dotted wildcard, same grammar as the kernel bus).

F-8 adds memory-poisoning guards: provenance + confidence quarantine on
writes so adversarial or low-trust posts are journaled but excluded from
the live read surface by default.

The blackboard is a thin layer over the kernel EventBus: posting emits
``blackboard.posted``, quarantine emits ``blackboard.quarantined``,
expiry emits ``blackboard.expired`` on sweep, and the bus's replay gives
late joiners the current surface for free.

Pure domain, deterministic under an injected clock.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Union

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
    provenance: str = ""
    quarantined: bool = False

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
            "provenance": self.provenance,
            "quarantined": self.quarantined,
        }


def _payload_bytes(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8"))


def is_poisonous(
    entry: BlackboardEntry,
    *,
    min_confidence: float = 0.2,
    require_provenance: bool = False,
    blocked_producers: Union[frozenset, Set[str]] = frozenset(),
    max_payload_bytes: int = 65536,
) -> bool:
    """Return True when *entry* fails the same poison-guard rules as Blackboard.post."""
    if entry.confidence < min_confidence:
        return True
    if require_provenance and not (entry.provenance or "").strip():
        return True
    if entry.producer in blocked_producers:
        return True
    if _payload_bytes(entry.payload) > max_payload_bytes:
        return True
    return False


class Blackboard:
    """TTL'd typed knowledge surface shared by the swarm."""

    def __init__(
        self,
        *,
        bus: Optional[EventBus] = None,
        clock: Optional[Callable[[], float]] = None,
        min_confidence: float = 0.2,
        require_provenance: bool = False,
        blocked_producers: Union[frozenset, Set[str]] = frozenset(),
        max_payload_bytes: int = 65536,
    ) -> None:
        self._bus = bus
        self._now = clock or time.time
        self._entries: Dict[str, BlackboardEntry] = {}
        self.posts = 0
        self.expiries = 0
        self.quarantines = 0
        self.min_confidence = float(min_confidence)
        self.require_provenance = bool(require_provenance)
        self.blocked_producers: frozenset[str] = frozenset(blocked_producers)
        self.max_payload_bytes = int(max_payload_bytes)

    def _emit(self, topic: str, entry: BlackboardEntry) -> None:
        if self._bus is None:
            return
        try:
            self._bus.emit(topic, entry.to_dict(),
                           correlation_id=f"bb_{entry.producer}")
        except Exception:
            pass

    def _should_quarantine(self, entry: BlackboardEntry) -> bool:
        return is_poisonous(
            entry,
            min_confidence=self.min_confidence,
            require_provenance=self.require_provenance,
            blocked_producers=self.blocked_producers,
            max_payload_bytes=self.max_payload_bytes,
        )

    def post(
        self,
        topic: str,
        payload: Dict[str, Any],
        *,
        producer: str,
        confidence: float = 0.5,
        ttl_s: float = 300.0,
        provenance: str = "",
    ) -> BlackboardEntry:
        payload = dict(payload)
        size = _payload_bytes(payload)
        if size > self.max_payload_bytes:
            raise ValueError(
                f"blackboard payload exceeds max_payload_bytes "
                f"({size} > {self.max_payload_bytes})"
            )

        entry = BlackboardEntry(
            entry_id=uuid.uuid4().hex[:12],
            topic=topic,
            payload=payload,
            producer=producer,
            confidence=min(1.0, max(0.0, confidence)),
            posted_at=self._now(),
            ttl_s=ttl_s,
            provenance=provenance or "",
            quarantined=False,
        )

        # Size already rejected above; remaining poison rules → quarantine.
        if self._should_quarantine(entry):
            entry.quarantined = True

        self._entries[entry.entry_id] = entry
        self.posts += 1
        self._emit("blackboard.posted", entry)

        if entry.quarantined:
            self.quarantines += 1
            self._emit("blackboard.quarantined", entry)

        return entry

    def read(
        self,
        topic: Optional[str] = None,
        *,
        include_quarantined: bool = False,
    ) -> List[BlackboardEntry]:
        """Live entries, optionally filtered to one topic.

        Quarantined entries are excluded unless ``include_quarantined`` is True.
        """
        now = self._now()
        out = [
            e for e in self._entries.values()
            if not e.is_expired(now)
            and (topic is None or e.topic == topic)
            and (include_quarantined or not e.quarantined)
        ]
        out.sort(key=lambda e: (-e.confidence, e.posted_at))
        return out

    def quarantine(self, entry_id: str) -> BlackboardEntry:
        """Operator: mark an existing entry as quarantined (hidden from read)."""
        entry = self._entries.get(entry_id)
        if entry is None:
            raise KeyError(f"unknown blackboard entry: {entry_id}")
        if not entry.quarantined:
            entry.quarantined = True
            self.quarantines += 1
            self._emit("blackboard.quarantined", entry)
        return entry

    def release(self, entry_id: str) -> BlackboardEntry:
        """Operator: clear quarantine so the entry returns to live read()."""
        entry = self._entries.get(entry_id)
        if entry is None:
            raise KeyError(f"unknown blackboard entry: {entry_id}")
        entry.quarantined = False
        return entry

    def sweep(self) -> List[str]:
        """Expire stale entries; returns their ids."""
        now = self._now()
        expired = [eid for eid, e in self._entries.items() if e.is_expired(now)]
        for eid in expired:
            entry = self._entries.pop(eid)
            self.expiries += 1
            self._emit("blackboard.expired", entry)
        return expired

    def stats(self) -> Dict[str, Any]:
        now = self._now()
        quarantined_live = sum(
            1 for e in self._entries.values()
            if e.quarantined and not e.is_expired(now)
        )
        return {
            "live": len(self.read()),
            "posts": self.posts,
            "expiries": self.expiries,
            "quarantined": quarantined_live,
            "quarantines": self.quarantines,
            "topics": sorted({e.topic for e in self._entries.values()}),
        }
