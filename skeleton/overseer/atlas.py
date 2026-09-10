"""
Skeleton Overseer — Capability Atlas

The complete living map of what the engine can do, on this device,
right now: every capability, its resource cost, its current
availability, and the path to unlock more. The atlas is how the
engine (and the user) answers "what can you do here?" honestly.

Structure:
- Capability: one engine capability (control loop class, retrieval
  class, federation class, fabric class, support class, recovery
  class) with resource envelope (cpu_w, mem_mb, min device class)
- AvailabilityGate: computes per-capability availability from the
  active budget, device profile, and engine state — available /
  degraded / unavailable, with the reason and the unlock hint
- Atlas: the full map + summary views (by class, by availability)
  and a user-facing narration for "what can you do?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEVICE_RANK = {"embedded": 0, "mobile": 1, "laptop": 2, "workstation": 3, "server": 4}


@dataclass
class Capability:
    """One engine capability with its resource envelope."""
    name: str
    cls: str  # control | retrieval | federation | fabric | support | recovery
    description: str
    min_device: str = "embedded"
    cpu_weight: float = 0.1     # relative CPU demand
    mem_mb: int = 32
    tier: str = "interactive"   # QoS tier it draws from

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "class": self.cls, "description": self.description,
                "min_device": self.min_device, "cpu_weight": self.cpu_weight,
                "mem_mb": self.mem_mb, "tier": self.tier}


CAPABILITIES: List[Capability] = [
    # Control
    Capability("governor.throttle", "control", "Per-resource throttle budgets", "embedded", 0.05, 16, "critical"),
    Capability("engine.pid_control", "control", "PID regulation with QoS arbitration", "mobile", 0.12, 32, "critical"),
    Capability("engine.mpc", "control", "Receding-horizon model-predictive control", "laptop", 0.25, 64, "interactive"),
    Capability("engine.meta_cognition", "control", "Self-scoring + bounded self-rewrite", "laptop", 0.15, 48, "background"),
    # Retrieval
    Capability("rag.vector", "retrieval", "Dense vector retrieval", "embedded", 0.08, 48, "interactive"),
    Capability("rag.agentic", "retrieval", "Agentic classify-plan-refine retrieval", "laptop", 0.2, 96, "interactive"),
    Capability("rag.citations", "retrieval", "KAG-grounded answer citations", "mobile", 0.05, 24, "interactive"),
    # Federation
    Capability("galaxy.messaging", "federation", "Node-to-node transport", "mobile", 0.06, 24, "background"),
    Capability("galaxy.consensus", "federation", "Raft-lite distributed consensus", "laptop", 0.1, 32, "background"),
    Capability("galaxy.kag_sync", "federation", "Federated knowledge replication", "laptop", 0.12, 64, "background"),
    Capability("fleet.governance", "federation", "Fleet-wide budget coordination", "workstation", 0.15, 64, "background"),
    # Fabric
    Capability("fabric.workorders", "fabric", "Work-order parsing + distillation", "embedded", 0.06, 32, "interactive"),
    Capability("fabric.oracle", "fabric", "Fate-matrix prediction + golden path", "laptop", 0.1, 48, "background"),
    Capability("fabric.backlog_chain", "fabric", "Idle-mined backlog blockchain", "mobile", 0.08, 32, "deferrable"),
    # Support
    Capability("support.lazy_planes", "support", "On-demand support plane loading", "mobile", 0.05, 24, "background"),
    Capability("support.agentic_heal", "support", "Backlog healing + sentinel validation", "laptop", 0.08, 40, "background"),
    # Recovery
    Capability("recovery.self_heal", "recovery", "Fault classification + playbook repair", "laptop", 0.1, 40, "critical"),
    Capability("recovery.cure_ledger", "recovery", "Learned cure-rate tracking", "workstation", 0.05, 24, "background"),
]


@dataclass
class Availability:
    """Computed availability of one capability right now."""
    capability: Capability
    state: str  # available | degraded | unavailable
    reason: str
    unlock_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out = self.capability.to_dict()
        out.update({"state": self.state, "reason": self.reason, "unlock_hint": self.unlock_hint})
        return out


class AvailabilityGate:
    """Computes capability availability from device + budget + state."""

    def evaluate(self, cap: Capability, device_class: str,
                 throttle: float, tier_shares: Dict[str, float]) -> Availability:
        dev_rank = DEVICE_RANK.get(device_class, 2)
        min_rank = DEVICE_RANK.get(cap.min_device, 0)

        if dev_rank < min_rank:
            return Availability(cap, "unavailable",
                                f"requires {cap.min_device}-class hardware",
                                f"run on {cap.min_device} or better")

        share = tier_shares.get(cap.tier, 0.0)
        if cap.tier == "critical":
            return Availability(cap, "available", "critical tier always runs")
        if share <= 0.0:
            return Availability(cap, "unavailable",
                                f"{cap.tier} tier shed under pressure",
                                "wait for pressure to ease or reduce load")
        if throttle < 0.5 or share < 0.1:
            return Availability(cap, "degraded",
                                f"running at reduced capacity (throttle {throttle:.0%})",
                                "full capacity when throttle recovers")
        return Availability(cap, "available", "nominal")


class CapabilityAtlas:
    """The living map of everything the engine can do here."""

    def __init__(self):
        self._gate = AvailabilityGate()
        self._evaluations: Dict[str, Availability] = {}

    def evaluate(self, device_class: str, throttle: float,
                 tier_shares: Dict[str, float]) -> Dict[str, Availability]:
        self._evaluations = {
            cap.name: self._gate.evaluate(cap, device_class, throttle, tier_shares)
            for cap in CAPABILITIES
        }
        return self._evaluations

    def summary(self) -> Dict[str, Any]:
        by_state: Dict[str, int] = {}
        by_class: Dict[str, int] = {}
        for av in self._evaluations.values():
            by_state[av.state] = by_state.get(av.state, 0) + 1
            by_class[av.capability.cls] = by_class.get(av.capability.cls, 0) + 1
        return {
            "total": len(self._evaluations),
            "by_state": by_state,
            "by_class": by_class,
            "available": [n for n, a in self._evaluations.items() if a.state == "available"],
            "degraded": [n for n, a in self._evaluations.items() if a.state == "degraded"],
            "unavailable": [n for n, a in self._evaluations.items() if a.state == "unavailable"],
        }

    def narrate(self) -> str:
        """User-facing answer to 'what can you do on this device?'"""
        s = self.summary()
        parts = []
        if s["by_state"].get("available"):
            parts.append(f"{s['by_state']['available']} capabilities at full strength")
        if s["by_state"].get("degraded"):
            parts.append(f"{s['by_state']['degraded']} running reduced")
        if s["by_state"].get("unavailable"):
            hints = [a.unlock_hint for a in self._evaluations.values()
                     if a.state == "unavailable" and a.unlock_hint]
            parts.append(f"{s['by_state']['unavailable']} locked ({hints[0] if hints else 'hardware limits'})")
        return "On this device: " + "; ".join(parts) + "."
