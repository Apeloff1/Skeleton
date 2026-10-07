"""
Skeleton Support — Loading Queue

On-demand plane loading with minimal resident footprint and maximal
possible load. Primary planes are always resident; support planes and
non-primary contexts load only when pressure signals justify them,
unload when idle past TTL.

Design:
- Pressure signals: primary plane stats (backlog size, queue depth,
  validation failures) cross thresholds → support plane requested
- Loading is staged through a bounded queue so mass simultaneous
  loads can't spike resources (max_loads_in_flight)
- Idle planes unload after TTL, returning resources; LRU order
  decides which loaded plane yields first when the resident cap hits
- All loading/unloading is observable on the bus
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class LoadRequest:
    """A queued request to load a plane."""
    request_id: str
    plane_name: str
    priority: float = 1.0
    reason: str = ""
    requested_at: float = field(default_factory=time.time)


@dataclass
class LoadedPlane:
    """A resident plane with lifecycle metadata."""
    name: str
    instance: Any
    loaded_at: float
    last_used: float
    loads: int = 1


class LoadingQueue:
    """Staged on-demand loader with resident-cap and idle eviction.

    Parameters:
    - max_in_flight: how many loads may stage at once (spike guard)
    - max_resident:  how many planes may stay loaded (memory guard)
    - idle_ttl:      seconds without use before a plane unloads
    """

    def __init__(self, bus: Optional[EventBus] = None,
                 max_in_flight: int = 2, max_resident: int = 4, idle_ttl: float = 120.0):
        self._bus = bus
        self.max_in_flight = max_in_flight
        self.max_resident = max_resident
        self.idle_ttl = idle_ttl

        self._factories: Dict[str, Callable[[], Any]] = {}
        self._queue: Deque[LoadRequest] = deque()
        self._resident: Dict[str, LoadedPlane] = {}
        self._pressure: Dict[str, float] = {}
        self._stats = {"requested": 0, "loaded": 0, "unloaded": 0, "evicted": 0,
                       "queue_drops": 0, "touches": 0}

    # --- Registration -------------------------------------------------------

    def register(self, plane_name: str, factory: Callable[[], Any]) -> None:
        """Register a lazy factory for a plane (nothing loads yet)."""
        self._factories[plane_name] = factory

    # --- Pressure-driven requests --------------------------------------------

    def signal_pressure(self, plane_name: str, level: float, reason: str = "") -> bool:
        """Record pressure for a plane; queue a load if warranted."""
        self._pressure[plane_name] = level
        if plane_name in self._resident:
            return True  # already loaded — pressure satisfied
        if plane_name not in self._factories:
            return False
        if any(r.plane_name == plane_name for r in self._queue):
            return True  # already queued

        request = LoadRequest(
            request_id=str(uuid.uuid4())[:8],
            plane_name=plane_name,
            priority=level,
            reason=reason,
        )
        # Bounded queue: drop lowest-priority request when full
        if len(self._queue) >= self.max_in_flight * 4:
            lowest = min(self._queue, key=lambda r: r.priority)
            if lowest.priority >= level:
                self._stats["queue_drops"] += 1
                return False
            self._queue.remove(lowest)
        self._queue.append(request)
        self._stats["requested"] += 1
        return True

    # --- Loading cycle ---------------------------------------------------------

    def pump(self) -> List[str]:
        """Process the loading queue up to max_in_flight. Returns loaded names."""
        loaded_now: List[str] = []
        in_flight = 0

        for request in sorted(self._queue, key=lambda r: r.priority, reverse=True):
            if in_flight >= self.max_in_flight:
                break
            self._queue.remove(request)
            in_flight += 1
            plane = self._load(request.plane_name)
            if plane is not None:
                loaded_now.append(request.plane_name)

        self._evict_idle()
        return loaded_now

    def _load(self, plane_name: str) -> Optional[Any]:
        if plane_name in self._resident:
            return self._resident[plane_name].instance
        factory = self._factories.get(plane_name)
        if factory is None:
            return None

        # Resident cap: evict LRU before loading
        if len(self._resident) >= self.max_resident:
            lru = min(self._resident.values(), key=lambda p: p.last_used)
            self._unload(lru.name, evicted=True)

        try:
            instance = factory()
        except Exception:
            return None

        self._resident[plane_name] = LoadedPlane(
            name=plane_name, instance=instance,
            loaded_at=time.time(), last_used=time.time(),
        )
        self._stats["loaded"] += 1
        if self._bus:
            self._bus.publish(DomainEvent(
                topic="support.loader.loaded",
                payload={"plane": plane_name, "resident": len(self._resident)},
            ))
        return instance

    # --- Access + eviction ------------------------------------------------------

    def get(self, plane_name: str) -> Optional[Any]:
        """Access a resident plane (touch for LRU); load on demand if queued."""
        self._stats["touches"] += 1
        if plane_name in self._resident:
            self._resident[plane_name].last_used = time.time()
            return self._resident[plane_name].instance
        # Demand-load immediately if registered
        return self._load(plane_name)

    def _evict_idle(self) -> None:
        now = time.time()
        for name, plane in list(self._resident.items()):
            if now - plane.last_used > self.idle_ttl:
                self._unload(name)

    def _unload(self, plane_name: str, evicted: bool = False) -> None:
        if plane_name in self._resident:
            del self._resident[plane_name]
            self._stats["unloaded"] += 1
            if evicted:
                self._stats["evicted"] += 1
            if self._bus:
                self._bus.publish(DomainEvent(
                    topic="support.loader.unloaded",
                    payload={"plane": plane_name, "evicted": evicted},
                ))

    # --- Introspection ------------------------------------------------------------

    def resident_planes(self) -> List[str]:
        return sorted(self._resident.keys())

    def footprint(self) -> Dict[str, Any]:
        """Resource usage report: the hardware-software equilibrium view."""
        return {
            "resident": len(self._resident),
            "resident_cap": self.max_resident,
            "queued": len(self._queue),
            "in_flight_cap": self.max_in_flight,
            "pressure": dict(self._pressure),
            "efficiency": round(self._stats["loaded"] / max(1, self._stats["touches"]), 3),
        }

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "footprint": self.footprint()}
