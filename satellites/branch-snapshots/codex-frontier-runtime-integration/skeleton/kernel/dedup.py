"""Idempotent delivery — dedup ledger for at-least-once event transports.

The bus delivers at-least-once by design (retries, redeliveries after
partition healing). Subscribers, however, want effectively-once
semantics. This module is the dedup side of that contract: a bounded
ledger of seen event ids with TTL expiry, plus a two-phase
mark/confirm protocol so a subscriber that crashes mid-handler does
not lose the event forever.

- :class:`DedupLedger` — seen-set with monotonic timestamps, lazy TTL
  eviction, hard capacity bound with oldest-first eviction.
- :class:`DeliveryTracker` — mark_in_flight / confirm / release trio;
  in-flight entries that time out become deliverable again.
- :class:`DuplicateDelivery` — raised on hard-duplicate confirms.

No threads, no deps; callers drive time via an injectable clock.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

from .errors import EventBusError


class DuplicateDelivery(EventBusError):
    code = "KRN.DUPLICATE_DELIVERY"


class DeliveryState(str, Enum):
    IN_FLIGHT = "IN_FLIGHT"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True)
class Admission:
    event_id: str
    is_duplicate: bool
    state: DeliveryState


class DedupLedger:
    """Bounded seen-set with TTL. Oldest entries evict first."""

    def __init__(
        self,
        *,
        ttl_s: float = 300.0,
        capacity: int = 100_000,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if ttl_s <= 0 or capacity <= 0:
            raise EventBusError(
                "ledger ttl and capacity must be positive",
                context={"ttl_s": ttl_s, "capacity": capacity},
            )
        self.ttl_s = ttl_s
        self.capacity = capacity
        self._now = clock or time.monotonic
        self._seen: "OrderedDict[str, float]" = OrderedDict()

    def _evict(self) -> None:
        now = self._now()
        while self._seen:
            event_id, ts = next(iter(self._seen.items()))
            if now - ts > self.ttl_s:
                self._seen.popitem(last=False)
            else:
                break
        while len(self._seen) >= self.capacity:
            self._seen.popitem(last=False)

    def seen(self, event_id: str) -> bool:
        self._evict()
        return event_id in self._seen

    def record(self, event_id: str) -> None:
        self._evict()
        self._seen[event_id] = self._now()
        self._seen.move_to_end(event_id)

    def __len__(self) -> int:
        self._evict()
        return len(self._seen)


class DeliveryTracker:
    """Two-phase dedup: admit → (handler runs) → confirm or release."""

    def __init__(
        self,
        *,
        ttl_s: float = 300.0,
        in_flight_timeout_s: float = 30.0,
        capacity: int = 100_000,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._now = clock or time.monotonic
        self.in_flight_timeout_s = in_flight_timeout_s
        self.ledger = DedupLedger(ttl_s=ttl_s, capacity=capacity, clock=self._now)
        self._in_flight: Dict[str, float] = {}

    def admit(self, event_id: str) -> Admission:
        """Decide whether an inbound delivery should be processed."""
        if self.ledger.seen(event_id):
            return Admission(event_id, True, DeliveryState.CONFIRMED)
        started = self._in_flight.get(event_id)
        if started is not None:
            if self._now() - started < self.in_flight_timeout_s:
                return Admission(event_id, True, DeliveryState.IN_FLIGHT)
            # Previous handler presumably died; allow redelivery.
        self._in_flight[event_id] = self._now()
        return Admission(event_id, False, DeliveryState.IN_FLIGHT)

    def confirm(self, event_id: str) -> None:
        """Handler finished successfully — the event will never redeliver."""
        self._in_flight.pop(event_id, None)
        if self.ledger.seen(event_id):
            raise DuplicateDelivery(
                "event already confirmed",
                context={"event_id": event_id},
            )
        self.ledger.record(event_id)

    def release(self, event_id: str) -> None:
        """Handler failed — make the event deliverable again immediately."""
        self._in_flight.pop(event_id, None)

    def in_flight_count(self) -> int:
        return len(self._in_flight)

    def stats(self) -> Dict[str, object]:
        return {
            "confirmed": len(self.ledger),
            "in_flight": self.in_flight_count(),
        }
