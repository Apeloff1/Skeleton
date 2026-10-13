"""Service mesh-lite: peer health (active probes + passive outlier ejection).

A :class:`PeerSet` tracks the endpoints of one upstream service:

* **Active health probes** — :meth:`PeerSet.probe_all` calls
  ``probe(endpoint) -> bool`` for each endpoint (the caller schedules it;
  no background threads). ``unhealthy_threshold`` consecutive probe
  failures mark an endpoint ``UNHEALTHY``; ``healthy_threshold``
  consecutive successes bring it back.
* **Passive outlier detection** — every client call reports success or
  failure; ``consecutive_failures`` failures *eject* the endpoint for
  ``base_ejection_s * 2^(ejections-1)`` (capped at ``max_ejection_s``).
  At most ``max_ejection_percent`` of endpoints may be ejected at once, so
  a dependency-wide outage degrades to "try everyone" instead of "no one".
* **Draining** — :meth:`PeerSet.drain` stops new picks for an endpoint
  while in-flight calls finish (graceful deploys).

Selection lives in :mod:`skeleton.gate_plane.mesh.routing`. Everything reads
time through the injectable :class:`~skeleton.gate_plane.s2s.clock.Clock`.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional

from skeleton.gate_plane.s2s.clock import Clock, system_clock

_ENDPOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class PeerState(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    EJECTED = "ejected"
    DRAINING = "draining"


@dataclass(frozen=True)
class Endpoint:
    id: str
    address: str
    weight: float = 1.0
    zone: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not _ENDPOINT_ID_RE.match(self.id or ""):
            raise ValueError(f"invalid endpoint id {self.id!r}")
        if not self.address:
            raise ValueError("endpoint address required")
        if not (self.weight > 0):
            raise ValueError("endpoint weight must be > 0")


@dataclass(frozen=True)
class HealthConfig:
    unhealthy_threshold: int = 2
    healthy_threshold: int = 2
    consecutive_failures: int = 5
    base_ejection_s: float = 10.0
    max_ejection_s: float = 300.0
    max_ejection_percent: float = 0.5

    def __post_init__(self) -> None:
        if self.unhealthy_threshold < 1 or self.healthy_threshold < 1 or self.consecutive_failures < 1:
            raise ValueError("thresholds must be >= 1")
        if self.base_ejection_s <= 0 or self.max_ejection_s < self.base_ejection_s:
            raise ValueError("need 0 < base_ejection_s <= max_ejection_s")
        if not 0.0 <= self.max_ejection_percent <= 1.0:
            raise ValueError("max_ejection_percent must be within [0, 1]")


@dataclass
class PeerHealth:
    endpoint: Endpoint
    probe_ok_streak: int = 0
    probe_fail_streak: int = 0
    probe_healthy: bool = True
    call_fail_streak: int = 0
    ejections: int = 0
    ejected_until: Optional[float] = None
    draining: bool = False
    in_flight: int = 0
    successes: int = 0
    failures: int = 0
    last_probe_at: Optional[float] = None

    def state(self, now: float) -> PeerState:
        if self.draining:
            return PeerState.DRAINING
        if self.ejected_until is not None and now < self.ejected_until:
            return PeerState.EJECTED
        if not self.probe_healthy:
            return PeerState.UNHEALTHY
        return PeerState.HEALTHY

    def as_dict(self, now: float) -> Dict[str, Any]:
        return {
            "id": self.endpoint.id,
            "address": self.endpoint.address,
            "zone": self.endpoint.zone,
            "weight": self.endpoint.weight,
            "state": self.state(now).value,
            "in_flight": self.in_flight,
            "ejections": self.ejections,
            "ejected_until": self.ejected_until,
            "successes": self.successes,
            "failures": self.failures,
        }


Probe = Callable[[Endpoint], bool]
StateListener = Callable[[str, str, PeerState, PeerState], None]


class PeerSet:
    """Endpoints of one upstream plus their health."""

    def __init__(
        self,
        service: str,
        endpoints: Iterable[Endpoint] = (),
        *,
        config: Optional[HealthConfig] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        self.service = service
        self.config = config or HealthConfig()
        self.clock: Clock = clock or system_clock()
        self._peers: Dict[str, PeerHealth] = {}
        self._lock = threading.RLock()
        self._listeners: List[StateListener] = []
        for ep in endpoints:
            self.add(ep)

    # -- membership ----------------------------------------------------

    def add(self, endpoint: Endpoint) -> None:
        with self._lock:
            if endpoint.id in self._peers:
                raise ValueError(f"duplicate endpoint {endpoint.id!r}")
            self._peers[endpoint.id] = PeerHealth(endpoint)

    def remove(self, endpoint_id: str) -> None:
        with self._lock:
            self._peers.pop(endpoint_id, None)

    def drain(self, endpoint_id: str, draining: bool = True) -> None:
        self._mutate(endpoint_id, lambda h: setattr(h, "draining", draining))

    def endpoints(self) -> List[Endpoint]:
        with self._lock:
            return [h.endpoint for h in self._peers.values()]

    def get(self, endpoint_id: str) -> Optional[PeerHealth]:
        with self._lock:
            return self._peers.get(endpoint_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._peers)

    def add_listener(self, fn: StateListener) -> None:
        self._listeners.append(fn)

    def _mutate(self, endpoint_id: str, fn: Callable[[PeerHealth], None]) -> None:
        now = self.clock.monotonic()
        with self._lock:
            h = self._peers.get(endpoint_id)
            if h is None:
                return
            before = h.state(now)
            fn(h)
            after = h.state(now)
        if before is not after:
            for listener in list(self._listeners):
                try:
                    listener(self.service, endpoint_id, before, after)
                except Exception:  # noqa: BLE001
                    pass

    # -- health --------------------------------------------------------

    def state_of(self, endpoint_id: str) -> Optional[PeerState]:
        with self._lock:
            h = self._peers.get(endpoint_id)
            return None if h is None else h.state(self.clock.monotonic())

    def record_probe(self, endpoint_id: str, ok: bool) -> None:
        cfg = self.config
        now = self.clock.monotonic()

        def apply(h: PeerHealth) -> None:
            h.last_probe_at = now
            if ok:
                h.probe_ok_streak += 1
                h.probe_fail_streak = 0
                if not h.probe_healthy and h.probe_ok_streak >= cfg.healthy_threshold:
                    h.probe_healthy = True
            else:
                h.probe_fail_streak += 1
                h.probe_ok_streak = 0
                if h.probe_healthy and h.probe_fail_streak >= cfg.unhealthy_threshold:
                    h.probe_healthy = False

        self._mutate(endpoint_id, apply)

    def probe_all(self, probe: Probe) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for ep in self.endpoints():
            try:
                ok = bool(probe(ep))
            except Exception:  # noqa: BLE001 - a crashing probe is a failed probe
                ok = False
            self.record_probe(ep.id, ok)
            results[ep.id] = ok
        return results

    def _ejected_count(self, now: float) -> int:
        return sum(1 for h in self._peers.values() if h.ejected_until is not None and now < h.ejected_until)

    def record_result(self, endpoint_id: str, ok: bool) -> None:
        cfg = self.config
        now = self.clock.monotonic()

        def apply(h: PeerHealth) -> None:
            if ok:
                h.successes += 1
                h.call_fail_streak = 0
                return
            h.failures += 1
            h.call_fail_streak += 1
            if h.call_fail_streak < cfg.consecutive_failures:
                return
            already = h.ejected_until is not None and now < h.ejected_until
            if already:
                return
            total = len(self._peers)
            if total and (self._ejected_count(now) + 1) / total > cfg.max_ejection_percent:
                return
            h.ejections += 1
            duration = min(cfg.max_ejection_s, cfg.base_ejection_s * (2 ** (h.ejections - 1)))
            h.ejected_until = now + duration
            h.call_fail_streak = 0

        with self._lock:
            self._mutate(endpoint_id, apply)

    def acquire(self, endpoint_id: str) -> None:
        self._mutate(endpoint_id, lambda h: setattr(h, "in_flight", h.in_flight + 1))

    def release(self, endpoint_id: str) -> None:
        self._mutate(endpoint_id, lambda h: setattr(h, "in_flight", max(0, h.in_flight - 1)))

    def available(self) -> List[PeerHealth]:
        """Endpoints eligible for new calls (healthy); falls back to unhealthy/ejected (not draining)."""
        now = self.clock.monotonic()
        with self._lock:
            peers = list(self._peers.values())
        healthy = [h for h in peers if h.state(now) is PeerState.HEALTHY]
        if healthy:
            return healthy
        # Panic mode: better to try a suspect peer than to fail every call.
        return [h for h in peers if h.state(now) is not PeerState.DRAINING]

    def snapshot(self) -> List[Dict[str, Any]]:
        now = self.clock.monotonic()
        with self._lock:
            return [h.as_dict(now) for h in self._peers.values()]


__all__ = ["Endpoint", "HealthConfig", "PeerHealth", "PeerSet", "PeerState", "Probe"]
