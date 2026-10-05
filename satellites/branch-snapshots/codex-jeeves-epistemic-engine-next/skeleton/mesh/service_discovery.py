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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "service": self.service,
            "address": self.address,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "load": self.load,
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

    def heartbeat(self, instance_id: str, load: Optional[float] = None) -> bool:
        inst = self._instances.get(instance_id)
        if not inst:
            return False
        inst.last_heartbeat_ns = time.time_ns()
        if load is not None:
            inst.load = load
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

    def pick(self, service: str, strategy: str = "round_robin",
             capability: Optional[str] = None) -> Optional[Dict[str, Any]]:
        candidates = self.lookup(service, capability)
        if not candidates:
            return None
        if strategy == "least_loaded":
            return min(candidates, key=lambda c: c.get("load", 0.0))
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
