"""
Skeleton Overseer — Engine V2

The high-intricacy engine: predictive sensing + continuous control +
QoS arbitration + wear bookkeeping, unified into one in-app engine.

Pipeline per engine tick:

    raw hardware sample
    → SensorFusion: outlier-rejected, confidence-weighted channels
    → TrendForecaster: level+trend per channel, breach prediction
    → WorkloadProfiler: regime classification with dwell hysteresis
    → ControlCore.fast_tick: PID regulators + QoS arbitration
    → WearModel: thermal-time + throttle-duty bookkeeping
    → BudgetEnforcer: apply the controlled budget to consumers
    → verdict with full telemetry (regime, forecasts, allocations)

The V1 governor remains available; V2 supersedes it when wired.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.overseer.control import ControlCore, ControlDecision, QoSTier
from skeleton.overseer.governor import BudgetEnforcer, BudgetProfile, ResourceGovernor
from skeleton.overseer.hardware import HardwareProbe, HardwareState
from skeleton.overseer.predict import (
    SensorFusion,
    TrendForecaster,
    WearModel,
    WorkloadProfiler,
    WorkloadRegime,
)


@dataclass
class EngineV2Tick:
    """Full telemetry for one engine tick."""
    tick: int
    decision: ControlDecision
    fused: Dict[str, Any]
    forecasts: Dict[str, Any]
    wear: Dict[str, Any]
    budget: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "decision": self.decision.to_dict(),
            "fused": self.fused,
            "forecasts": self.forecasts,
            "wear": self.wear,
            "budget": self.budget,
        }


class OverseerEngineV2:
    """High-intricacy in-app engine: anticipate, regulate, arbitrate."""

    def __init__(self, bus: Optional[EventBus] = None,
                 probe: Optional[HardwareProbe] = None,
                 base_budget: Optional[BudgetProfile] = None):
        self._bus = bus
        self.probe = probe or HardwareProbe()
        self.governor = ResourceGovernor(probe=self.probe, bus=bus)
        self.base_budget = base_budget or self.governor.base_budget
        self.enforcer = BudgetEnforcer()

        self.fusion = SensorFusion()
        self.forecaster = TrendForecaster()
        self.profiler = WorkloadProfiler()
        self.control = ControlCore()
        self.wear = WearModel()

        self._ticks = 0
        self._history: List[EngineV2Tick] = []
        self._stats = {"ticks": 0, "anticipations": 0, "regime_changes": 0}
        self._last_regime: Optional[str] = None

    # --- Consumer binding (same interface as V1) ----------------------------

    def bind(self, name: str, apply_fn: Any) -> None:
        self.enforcer.attach(name, apply_fn)

    def bind_loader(self, loader: Any) -> None:
        def apply(budget: BudgetProfile) -> None:
            loader.max_resident = budget.max_resident_planes
            loader.max_in_flight = budget.max_in_flight_loads
        self.bind("loading_queue", apply)

    def bind_queue(self, queue: Any) -> None:
        self.bind("priority_queue", lambda b: setattr(queue, "capacity_override", b.queue_size))

    def bind_miner(self, backlog: Any) -> None:
        self.bind("backlog_miner", lambda b: setattr(backlog, "miner_interval", b.miner_interval_s))

    def bind_rag(self, rag: Any) -> None:
        self.bind("agentic_rag", lambda b: setattr(rag, "top_k_override", b.rag_top_k))

    # --- The tick ------------------------------------------------------------

    def tick(self, demand: Optional[float] = None, events: float = 0.0) -> EngineV2Tick:
        self._ticks += 1
        self._stats["ticks"] += 1

        # 1. Raw hardware sample
        hw = self.probe.read_state()

        # 2. Sensor fusion per channel
        fused = {
            "cpu": self.fusion.observe("cpu", hw.cpu_load),
            "memory": self.fusion.observe("memory", hw.memory_pressure),
            "thermal": self.fusion.observe("thermal", hw.thermal_max()),
            "battery": self.fusion.observe("battery", hw.battery_level if hw.battery_level is not None else 1.0),
            "io": self.fusion.observe("io", hw.io_wait),
        }

        # 3. Forecasts: trend + breach prediction on the two slow channels
        self.forecaster.observe("thermal", fused["thermal"].value)
        self.forecaster.observe("memory", fused["memory"].value)
        forecasts = {}
        thermal_fc = self.forecaster.forecast("thermal", steps=10, threshold=80.0)
        memory_fc = self.forecaster.forecast("memory", steps=10, threshold=0.9)
        if thermal_fc:
            forecasts["thermal"] = thermal_fc
        if memory_fc:
            forecasts["memory"] = memory_fc

        # 4. Workload regime from demand shape (default: cpu demand)
        demand_signal = demand if demand is not None else fused["cpu"].value
        workload = self.profiler.observe(demand_signal, events)
        if workload.regime != self._last_regime:
            self._stats["regime_changes"] += 1
            self._last_regime = workload.regime

        # 5. Control core: PID + arbitration (+ slow-loop setpoint adaptation)
        measurements = {
            "cpu": fused["cpu"].value,
            "memory": fused["memory"].value,
            "thermal": fused["thermal"].value,
            "battery": fused["battery"].value,
            "io": fused["io"].value,
        }
        decision = self.control.fast_tick(measurements, workload, forecasts)
        if decision.anticipatory:
            self._stats["anticipations"] += len(decision.anticipatory)

        # 6. Wear bookkeeping
        self.wear.observe(fused["thermal"].value, decision.aggregate)
        wear_report = self.wear.report()

        # 7. Apply the controlled budget to consumers
        budget = self.base_budget.scaled(decision.aggregate)
        applied = self.enforcer.apply(budget)

        tick = EngineV2Tick(
            tick=self._ticks,
            decision=decision,
            fused={k: {"value": round(c.value, 3), "confidence": c.confidence}
                   for k, c in fused.items()},
            forecasts={k: f.to_dict() for k, f in forecasts.items()},
            wear=wear_report.to_dict(),
            budget=budget.to_dict(),
        )
        self._history.append(tick)
        if len(self._history) > 64:
            self._history.pop(0)

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.engine_v2.tick",
                payload={
                    "aggregate": decision.aggregate,
                    "regime": decision.regime,
                    "anticipatory": decision.anticipatory,
                    "applied": applied,
                    "wear_index": wear_report.estimated_wear_index,
                },
                correlation_id=f"engine_v2_{self._ticks}",
            ))
        return tick

    # --- Surfaces -------------------------------------------------------------

    def tier_share(self, tier: str) -> float:
        """Current budget share for a QoS tier."""
        if not self._history:
            return 1.0
        for alloc in self._history[-1].decision.allocations:
            if alloc.tier == tier:
                return alloc.share
        return 0.0

    def status(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "device": self.governor.profile.to_dict(),
            "control": self.control.stats(),
            "wear": self.wear.report().to_dict(),
            "last_tick": self._history[-1].to_dict() if self._history else None,
            "consumers": self.enforcer.consumers(),
        }

    def history(self, n: int = 10) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._history[-n:]]
