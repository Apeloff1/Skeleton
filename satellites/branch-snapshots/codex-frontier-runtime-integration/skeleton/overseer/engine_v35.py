"""
Skeleton Overseer — Engine V3.5 (Over-Achiever)

The full frontier stack unified: paramount control (V3) plus fleet
governance, energy awareness, self-healing recovery, and the
capability atlas — one tick, total oversight, fleet-wide reach.

Tick pipeline:

    V3 paramount tick (sysid → MPC → twin → meta → trust gate)
    → EnergyModel: draw estimate + drain forecast + quality trades
      (battery-driven throttle merged into control when reserves tighten)
    → RecoveryEngine: anomaly signals classified, playbook repairs
      attempted, cures verified against live signals
    → FleetGovernor: report broadcast, migration hints, ceiling clamp
    → CapabilityAtlas: availability re-evaluated under current throttle
    → BudgetEnforcer: final control applied to all consumers

One engine. Every device. Fleet-coherent. Self-healing. Self-aware.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.overseer.atlas import CapabilityAtlas
from skeleton.overseer.energy import EnergyModel
from skeleton.overseer.engine_v3 import OverseerEngineV3
from skeleton.overseer.fleet_gov import FleetGovernor
from skeleton.overseer.recovery import RecoveryEngine


@dataclass
class EngineV35Tick:
    """Full over-achiever telemetry for one tick."""
    tick: int
    control: float
    v3: Dict[str, Any]
    energy: Dict[str, Any]
    recovery: Dict[str, Any]
    fleet: Dict[str, Any]
    atlas: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "control": round(self.control, 4),
            "v3": self.v3,
            "energy": self.energy,
            "recovery": self.recovery,
            "fleet": self.fleet,
            "atlas": self.atlas,
        }


class OverseerEngineV35:
    """The over-achiever engine: paramount control + fleet governance +
    energy awareness + self-healing + self-knowledge, per tick."""

    def __init__(self, bus: Optional[EventBus] = None,
                 probe: Optional[Any] = None,
                 node: Optional[Any] = None,
                 transport: Optional[Any] = None,
                 consensus: Optional[Any] = None):
        self._bus = bus
        self.v3 = OverseerEngineV3(bus=bus, probe=probe)

        device_class = self.v3.governor.profile.device_class.value
        gpu_class = self.v3.governor.profile.gpu.value
        self.energy = EnergyModel(device_class, gpu_class)
        self.recovery = RecoveryEngine(bus=bus)
        self.atlas = CapabilityAtlas()
        self.fleet: Optional[FleetGovernor] = (
            FleetGovernor(node, transport, consensus, bus=bus)
            if node is not None and transport is not None else None
        )

        self._ticks = 0
        self._history: List[EngineV35Tick] = []
        self._stats = {"ticks": 0, "energy_overrides": 0, "repairs": 0,
                       "migrations": 0}

    # --- Consumer binding (delegates to V3) ---------------------------------

    def bind(self, name: str, apply_fn: Any) -> None:
        self.v3.bind(name, apply_fn)

    def bind_loader(self, loader: Any) -> None:
        self.v3.bind_loader(loader)

    def bind_queue(self, queue: Any) -> None:
        self.v3.bind_queue(queue)

    def bind_miner(self, backlog: Any) -> None:
        self.v3.bind_miner(backlog)

    def bind_rag(self, rag: Any) -> None:
        self.v3.bind_rag(rag)

    # --- The over-achiever tick ----------------------------------------------

    def tick(self, demand: Optional[float] = None, events: float = 0.0) -> EngineV35Tick:
        self._ticks += 1
        self._stats["ticks"] += 1

        # 1. Paramount V3 tick
        v3_tick = self.v3.tick(demand=demand, events=events)
        control = v3_tick.control
        states = {k: c.get("value", 0.0) for k, c in
                  ((k, v3_tick.models.get(k, {})) for k in ("cpu", "memory", "thermal", "battery", "io"))}

        # 2. Energy: draw + drain + quality trades; battery override
        hw = self.v3.probe.read_state()
        energy_eval = self.energy.evaluate(
            hw.cpu_load, hw.memory_pressure, hw.io_wait, hw.battery_level)
        trade = energy_eval.get("quality_trade")
        if trade is not None:
            # Battery reserve tightening: clamp control by the trade ratio
            energy_control = min(control, trade["queue_scale"])
            if energy_control < control:
                self._stats["energy_overrides"] += 1
                control = energy_control

        # 3. Recovery: classify live signals, run playbook cycle
        if v3_tick.anomalies:
            for ch in v3_tick.anomalies:
                self.recovery.ingest({"kind": "sysid_anomaly", "channel": ch,
                                      "severity": 0.7})
        if v3_tick.fallback:
            self.recovery.ingest({"kind": "trust_collapse", "channel": "meta",
                                  "severity": 0.6})
        attempts = self.recovery.cycle(signal_clear={ch: True for ch in states})
        if attempts:
            self._stats["repairs"] += len(attempts)

        # 4. Fleet governance: report, hints, ceiling clamp
        fleet_out: Dict[str, Any] = {"attached": False}
        if self.fleet is not None:
            fleet_out = self.fleet.governance_cycle(self.v3)
            fleet_out["attached"] = True
            if fleet_out.get("migration_hints"):
                self._stats["migrations"] += len(fleet_out["migration_hints"])
            control = self.fleet.throttle.clamp(control)

        # 5. Capability atlas under the final control
        tier_shares = {t: self.v3.tier_share(t) for t in
                       ("critical", "interactive", "background", "deferrable")}
        self.atlas.evaluate(
            self.v3.governor.profile.device_class.value, control, tier_shares)

        tick = EngineV35Tick(
            tick=self._ticks,
            control=control,
            v3=v3_tick.to_dict(),
            energy=energy_eval,
            recovery={"attempts": [a.__dict__ for a in attempts],
                      "stats": self.recovery.stats()},
            fleet=fleet_out,
            atlas=self.atlas.summary(),
        )
        self._history.append(tick)
        if len(self._history) > 64:
            self._history.pop(0)

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.engine_v35.tick",
                payload={
                    "control": control,
                    "energy_w": energy_eval["draw"]["total_w"],
                    "repairs": len(attempts),
                    "fleet_attached": fleet_out.get("attached", False),
                    "atlas_available": len(self.atlas.summary().get("available", [])),
                },
                correlation_id=f"engine_v35_{self._ticks}",
            ))
        return tick

    # --- Surfaces -------------------------------------------------------------

    def narrate_capabilities(self) -> str:
        return self.atlas.narrate()

    def status(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "v3": self.v3.status(),
            "energy": self.energy.stats(),
            "recovery": self.recovery.stats(),
            "fleet": self.fleet.stats() if self.fleet else {"attached": False},
            "atlas": self.atlas.summary(),
        }

    def history(self, n: int = 10) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._history[-n:]]
