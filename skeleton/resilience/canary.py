"""Canary tokens — tripwires that turn exfiltration attempts into signals.

The fortress blocks known-bad input; canaries catch the attacker who
*doesn't* look bad yet. A canary is a fake secret planted in a plausible
place (a vault entry named `db_password_prod`, a memory chunk that reads
like an API key). Nothing legitimate ever touches a canary — so any read
is, by definition, reconnaissance or exfiltration.

Design
------
- Canaries are indistinguishable from real entries at the storage layer;
  only the registry knows which ids are armed.
- Every touch (read, query hit, export) is recorded with the caller's
  identity and published as a CRITICAL event. There is no legitimate
  access path, so there is no false-positive case to filter.
- Canaries are cheap: plant many, rotate their material on a schedule,
  and let the attacker reveal *which* store they breached by which
  canary fired — a breach triangulation for free.
"""

from __future__ import annotations

import hashlib
import secrets as _secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass(frozen=True)
class CanaryToken:
    canary_id: str
    location: str                    # where it's planted: "vault", "memory.rag", ...
    material: str                    # the fake secret value
    planted_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class TripEvent:
    canary_id: str
    location: str
    touched_by: str
    touched_at: float = field(default_factory=time.time)


class CanaryRegistry:
    """Plants, tracks, and fires on canary touches."""

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._canaries: Dict[str, CanaryToken] = {}
        self._trips: List[TripEvent] = []
        self._bus = bus

    def plant(self, location: str, *,
              material: Optional[str] = None) -> CanaryToken:
        """Mint a new canary for a location. Returns the token to store."""
        material = material or "sk-" + _secrets.token_hex(16)
        canary_id = "cnr_" + hashlib.sha256(
            f"{location}:{material}".encode()
        ).hexdigest()[:12]
        token = CanaryToken(canary_id=canary_id, location=location,
                            material=material)
        self._canaries[canary_id] = token
        return token

    def is_canary_material(self, value: str) -> Optional[CanaryToken]:
        """Match a value against all planted canaries (by material)."""
        for token in self._canaries.values():
            if token.material == value:
                return token
        return None

    def touch(self, value: str, *, touched_by: str) -> Optional[TripEvent]:
        """
        Report that a value was accessed. If it's canary material, the
        tripwire fires: recorded, published CRITICAL, returned.
        """
        token = self.is_canary_material(value)
        if token is None:
            return None
        trip = TripEvent(canary_id=token.canary_id, location=token.location,
                         touched_by=touched_by)
        self._trips.append(trip)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="resilience.canary.tripped",
                    payload={
                        "canary_id": token.canary_id,
                        "location": token.location,
                        "touched_by": touched_by,
                        "trips_total": len(self._trips),
                    },
                    correlation_id=f"cnr_{token.canary_id}",
                )
            )
        return trip

    def trips(self, *, location: Optional[str] = None) -> List[TripEvent]:
        return [t for t in self._trips if location is None or t.location == location]

    def stats(self) -> Dict[str, Any]:
        locations: Dict[str, int] = {}
        for t in self._canaries.values():
            locations[t.location] = locations.get(t.location, 0) + 1
        return {
            "canaries_planted": len(self._canaries),
            "by_location": locations,
            "trips": len(self._trips),
        }
