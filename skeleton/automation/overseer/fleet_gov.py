"""
Skeleton Overseer — Fleet Governance

Extends the paramount engine fleet-wide: every galaxy node runs its own
V3 engine, and their budgets coordinate. The fleet has one coherent
resource policy instead of N independent devices fighting for headroom.

Architecture:

- DeviceReport: each node's V3 status broadcast (device class, control,
  trust, wear, anomalies, regime) over the galaxy transport
- FleetRegistry: live view of every governed device with staleness
  tracking; the leader sees the whole fleet's envelope
- LoadMigrationAdvisor: when one device is saturated (control ≤ floor,
  thermal-critical, or wear-critical) and a peer has headroom for the
  same QoS tier, the advisor issues a migration hint: move deferrable
  and background work to the peer. Tiers migrate in shed order —
  deferrable first, interactive never mid-conversation.
- CoordinatedThrottle: the leader can propose a fleet-wide throttle
  level via consensus (datacenter power cap, shared thermal envelope);
  every node clamps its local control to the fleet ceiling until the
  proposal expires.

Wire messages:
- fleet.report    {device, control, trust, wear, regime, anomalies}
- fleet.migrate   {task_class, from, to, reason}
- fleet.throttle  {ceiling, term, reason, ttl}
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DeviceReport:
    """One governed device's status report for the fleet."""
    node_id: str
    device_class: str
    control: float
    trust: float
    wear_index: float
    regime: str
    anomalies: List[str] = field(default_factory=list)
    reported_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "device_class": self.device_class,
            "control": round(self.control, 3),
            "trust": round(self.trust, 3),
            "wear_index": round(self.wear_index, 4),
            "regime": self.regime,
            "anomalies": self.anomalies,
        }


class FleetRegistry:
    """Live view of every governed device in the fleet."""

    STALE_AFTER = 60.0

    def __init__(self):
        self._reports: Dict[str, DeviceReport] = {}

    def ingest(self, report: DeviceReport) -> None:
        self._reports[report.node_id] = report

    def devices(self, include_stale: bool = False) -> List[DeviceReport]:
        now = time.time()
        return [r for r in self._reports.values()
                if include_stale or now - r.reported_at < self.STALE_AFTER]

    def get(self, node_id: str) -> Optional[DeviceReport]:
        return self._reports.get(node_id)

    def saturated(self, control_floor: float = 0.3) -> List[DeviceReport]:
        return [r for r in self.devices() if r.control <= control_floor
                or r.wear_index >= 0.8 or r.anomalies]

    def with_headroom(self, control_ceiling: float = 0.6) -> List[DeviceReport]:
        return [r for r in self.devices() if r.control >= control_ceiling
                and r.wear_index < 0.5 and not r.anomalies]

    def summary(self) -> Dict[str, Any]:
        devices = self.devices()
        return {
            "devices": len(devices),
            "saturated": len(self.saturated()),
            "with_headroom": len(self.with_headroom()),
            "mean_control": round(sum(r.control for r in devices) / max(1, len(devices)), 3),
        }


@dataclass
class MigrationHint:
    """Advisory: move a class of work from one device to another."""
    hint_id: str
    task_class: str  # deferrable | background
    from_node: str
    to_node: str
    reason: str
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"hint_id": self.hint_id, "task_class": self.task_class,
                "from": self.from_node, "to": self.to_node, "reason": self.reason}


class LoadMigrationAdvisor:
    """Issues migration hints when saturation and headroom coexist."""

    MIGRATABLE = ("deferrable", "background")

    def __init__(self, registry: FleetRegistry):
        self._registry = registry
        self._hints: List[MigrationHint] = []
        self._stats = {"advised": 0, "suppressed": 0}

    def advise(self) -> List[MigrationHint]:
        hints: List[MigrationHint] = []
        saturated = self._registry.saturated()
        headroom = self._registry.with_headroom()
        if not saturated or not headroom:
            return hints

        for hot in saturated:
            # Pick the peer with the most headroom
            target = max(headroom, key=lambda r: r.control)
            if target.node_id == hot.node_id:
                continue
            reason_bits = []
            if hot.control <= 0.3:
                reason_bits.append(f"control {hot.control:.0%}")
            if hot.wear_index >= 0.8:
                reason_bits.append(f"wear {hot.wear_index:.0%}")
            if hot.anomalies:
                reason_bits.append("anomalies active")
            hint = MigrationHint(
                hint_id=str(uuid.uuid4())[:8],
                task_class=self.MIGRATABLE[0],
                from_node=hot.node_id,
                to_node=target.node_id,
                reason="; ".join(reason_bits),
            )
            hints.append(hint)
            self._hints.append(hint)
            self._stats["advised"] += 1

        # Suppress hint storms: max one per source node per advise cycle
        seen = set()
        unique = []
        for h in hints:
            if h.from_node not in seen:
                seen.add(h.from_node)
                unique.append(h)
            else:
                self._stats["suppressed"] += 1
        return unique

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)


class CoordinatedThrottle:
    """Fleet-wide throttle ceiling via consensus (shared power/thermal
    envelope). Nodes clamp local control to the ceiling until expiry."""

    def __init__(self, consensus: Optional[Any] = None):
        self._consensus = consensus
        self._ceiling: Optional[float] = None
        self._expires_at: float = 0.0
        self._term: int = 0
        self._stats = {"proposals": 0, "adopted": 0, "expired": 0}

    def propose(self, ceiling: float, ttl: float = 300.0, reason: str = "") -> bool:
        """Propose a fleet ceiling through consensus (or adopt directly
        when no consensus engine is attached)."""
        self._stats["proposals"] += 1
        accepted = True
        if self._consensus is not None:
            proposal = self._consensus.propose(
                "fleet.throttle",
                {"ceiling": ceiling, "ttl": ttl, "reason": reason},
                wait=True, timeout=3.0,
            )
            accepted = proposal.status == "accepted"
        if accepted:
            self._adopt(ceiling, ttl)
        return accepted

    def _adopt(self, ceiling: float, ttl: float) -> None:
        self._ceiling = ceiling
        self._expires_at = time.time() + ttl
        self._term += 1
        self._stats["adopted"] += 1

    def current_ceiling(self) -> Optional[float]:
        if self._ceiling is None:
            return None
        if time.time() > self._expires_at:
            self._ceiling = None
            self._stats["expired"] += 1
            return None
        return self._ceiling

    def clamp(self, local_control: float) -> float:
        """Clamp a local control value to the fleet ceiling."""
        ceiling = self.current_ceiling()
        return min(local_control, ceiling) if ceiling is not None else local_control

    def stats(self) -> Dict[str, Any]:
        return {**self._stats,
                "active_ceiling": self.current_ceiling(),
                "term": self._term}


class FleetGovernor:
    """The fleet-wide governance layer: reports in, advice out,
    ceilings coordinated."""

    def __init__(self, node: Any, transport: Any, consensus: Optional[Any] = None,
                 bus: Optional[Any] = None):
        self._node = node
        self._transport = transport
        self._bus = bus
        self.registry = FleetRegistry()
        self.advisor = LoadMigrationAdvisor(self.registry)
        self.throttle = CoordinatedThrottle(consensus)
        self._stats = {"reports_sent": 0, "reports_received": 0, "migrations": 0}

        transport.on("fleet.report", self._on_report)
        transport.on("fleet.migrate", self._on_migrate)

    def broadcast_report(self, engine_v3: Any) -> DeviceReport:
        """Build this node's report from its V3 engine and broadcast it."""
        status = engine_v3.status()
        report = DeviceReport(
            node_id=self._node.node_id,
            device_class=status["device"]["device_class"],
            control=status["control"],
            trust=status["meta"]["trust"],
            wear_index=status["wear"]["wear_index"],
            regime=status.get("meta", {}).get("regime", "unknown"),
            anomalies=status.get("anomalies", []) if isinstance(status.get("anomalies"), list) else [],
        )
        self.registry.ingest(report)  # self-report locally too
        for peer in self._node._registry.discover():
            self._transport.send(peer.address, {"type": "fleet.report", **report.to_dict()})
            self._stats["reports_sent"] += 1
        return report

    def _on_report(self, payload: Dict[str, Any]) -> None:
        self._stats["reports_received"] += 1
        self.registry.ingest(DeviceReport(
            node_id=payload["node_id"],
            device_class=payload["device_class"],
            control=payload["control"],
            trust=payload["trust"],
            wear_index=payload["wear_index"],
            regime=payload["regime"],
            anomalies=payload.get("anomalies", []),
        ))

    def _on_migrate(self, payload: Dict[str, Any]) -> None:
        if payload.get("to") == self._node.node_id:
            self._stats["migrations"] += 1
            if self._bus:
                self._bus.emit("fleet.migration.incoming", payload)

    def governance_cycle(self, engine_v3: Any) -> Dict[str, Any]:
        """One fleet governance pass: report, advise, clamp."""
        report = self.broadcast_report(engine_v3)
        hints = self.advisor.advise()
        ceiling = self.throttle.current_ceiling()
        clamped = self.throttle.clamp(report.control)
        return {
            "report": report.to_dict(),
            "fleet": self.registry.summary(),
            "migration_hints": [h.to_dict() for h in hints],
            "ceiling": ceiling,
            "clamped_control": round(clamped, 3),
        }

    def stats(self) -> Dict[str, Any]:
        return {**self._stats,
                "registry": self.registry.summary(),
                "advisor": self.advisor.stats(),
                "throttle": self.throttle.stats()}
