"""Service discovery — registry of subsystem instances with heartbeats.

Tracks live subsystem instances (name, address, metadata), expires
stale registrations via heartbeat TTL, supports lookup by capability,
and round-robin / least-loaded selection strategies. Feeds the mesh
card on the dashboard.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Instance:
    instance_id: str
    service: str
    address: str
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_ns: int = 0
    last_heartbeat_ns: int = 0
    load: float = 0.0
    latency_ms: float = 10.0
    error_rate: float = 0.0

    def health_score(self) -> float:
        load_factor = max(0.05, 1.0 - min(0.95, float(self.load)))
        err_factor = max(0.05, 1.0 - min(0.95, float(self.error_rate) * 5.0))
        lat_factor = 1.0 / (1.0 + max(0.0, float(self.latency_ms)) / 100.0)
        return round(load_factor * err_factor * lat_factor, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "service": self.service,
            "address": self.address,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "load": self.load,
            "latency_ms": round(self.latency_ms, 2),
            "error_rate": round(self.error_rate, 4),
            "health_score": self.health_score(),
            "age_s": (time.time_ns() - self.registered_ns) / 1e9,
        }


class ServiceRegistry:
    """Heartbeat-based service registry with capability routing."""

    def __init__(self, ttl_s: float = 30.0):
        self.ttl_s = ttl_s
        self._instances: Dict[str, Instance] = {}
        self._rr_counters: Dict[str, int] = {}

    def register(self, instance_id: str, service: str, address: str,
                 capabilities: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> Instance:
        now = time.time_ns()
        inst = Instance(
            instance_id=instance_id, service=service, address=address,
            capabilities=capabilities or [], metadata=metadata or {},
            registered_ns=now, last_heartbeat_ns=now,
        )
        self._instances[instance_id] = inst
        return inst

    def deregister(self, instance_id: str) -> bool:
        return self._instances.pop(instance_id, None) is not None

    def heartbeat(
        self,
        instance_id: str,
        load: Optional[float] = None,
        *,
        latency_ms: Optional[float] = None,
        error_rate: Optional[float] = None,
        capabilities: Optional[List[str]] = None,
    ) -> bool:
        inst = self._instances.get(instance_id)
        if not inst:
            return False
        inst.last_heartbeat_ns = time.time_ns()
        if load is not None:
            inst.load = float(load)
        if latency_ms is not None:
            inst.latency_ms = 0.7 * inst.latency_ms + 0.3 * max(0.0, float(latency_ms))
        if error_rate is not None:
            inst.error_rate = 0.7 * inst.error_rate + 0.3 * max(0.0, min(1.0, float(error_rate)))
        if capabilities is not None:
            inst.capabilities = list(capabilities)
        return True

    def _prune(self) -> None:
        cutoff = time.time_ns() - int(self.ttl_s * 1e9)
        dead = [iid for iid, i in self._instances.items() if i.last_heartbeat_ns < cutoff]
        for iid in dead:
            del self._instances[iid]

    def lookup(self, service: str, capability: Optional[str] = None) -> List[Dict[str, Any]]:
        self._prune()
        out = []
        for inst in self._instances.values():
            if inst.service != service:
                continue
            if capability and capability not in inst.capabilities:
                continue
            out.append(inst.to_dict())
        return out

    def pick(
        self,
        service: str,
        strategy: str = "round_robin",
        capability: Optional[str] = None,
        *,
        preferred_capabilities: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        candidates = self.lookup(service, capability)
        if not candidates:
            return None
        if strategy == "least_loaded":
            return min(candidates, key=lambda c: c.get("load", 0.0))
        if strategy == "adaptive_qos":
            prefs = set(preferred_capabilities or ())
            def _qos_key(c: Dict[str, Any]) -> float:
                base = float(c.get("health_score", 0.5))
                caps = set(c.get("capabilities") or ())
                affinity = (len(caps & prefs) / max(1, len(prefs))) if prefs else 0.0
                return base * (1.0 + 0.5 * affinity)
            return max(candidates, key=_qos_key)
        idx = self._rr_counters.get(service, 0) % len(candidates)
        self._rr_counters[service] = idx + 1
        return candidates[idx]

    def card(self) -> Dict[str, Any]:
        self._prune()
        by_service: Dict[str, int] = {}
        for inst in self._instances.values():
            by_service[inst.service] = by_service.get(inst.service, 0) + 1
        return {
            "kind": "service-registry-card",
            "instances": len(self._instances),
            "services": by_service,
            "ttl_s": self.ttl_s,
        }
