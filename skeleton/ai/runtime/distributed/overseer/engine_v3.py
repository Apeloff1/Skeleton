"""
Skeleton Overseer — Engine V3 (Paramount)

The beyond-human-scope engine: it doesn't just regulate the machine —
it maintains a live dynamical model OF the machine, optimizes over a
receding horizon, replays history through a digital twin to score its
own alternatives, and rewrites its own parameters when it detects
systematic miscalibration. Bounded, auditable, deterministic.

Tick pipeline:

    raw hardware sample
    → SensorFusion (V2 stack retained)
    → SystemIdentifier: RLS model update per channel (a, b, c)
    → anomaly scan: channels whose model is failing
    → MPC: receding-horizon optimization over trajectory library
      with HARD constraint walls (thermal/memory never crossed)
    → DigitalTwin: counterfactual grid over recent history
    → MetaCognition: scorecards + regret + trust + bounded rewrites
    → trust gate: low-trust decisions fall back to conservative control
    → BudgetEnforcer: apply the MPC-computed budget
    → full telemetry: models, plan, twin deltas, trust, rewrites

V1 throttles. V2 anticipates. V3 understands, plans, and improves itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.overseer.control import QoSArbiter, QoSTier
from skeleton.overseer.governor import BudgetEnforcer, BudgetProfile, ResourceGovernor
from skeleton.overseer.hardware import HardwareProbe
from skeleton.overseer.mpc import ModelPredictiveController, MPCResult, SystemIdentifier
from skeleton.overseer.predict import (
    SensorFusion,
    TrendForecaster,
    WearModel,
    WorkloadProfiler,
)
from skeleton.overseer.twin import DigitalTwin, MetaCognition


# Setpoints the MPC tracks (same envelopes as V2's control core)
V3_SETPOINTS: Dict[str, float] = {
    "cpu": 0.72,
    "memory": 0.68,
    "thermal": 66.0,
    "battery": 0.30,
    "io": 0.15,
}

CONSERVATIVE_FLOOR = 0.6  # trust below this → fall back to safe control


@dataclass
class EngineV3Tick:
    """Full telemetry for one paramount tick."""
    tick: int
    control: float
    mpc: Dict[str, Any]
    models: Dict[str, Any]
    anomalies: List[str]
    regime: str
    twin_deltas: List[Dict[str, Any]]
    trust: float
    fallback: bool
    rewrites: List[Dict[str, Any]]
    wear: Dict[str, Any]
    budget: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "control": round(self.control, 4),
            "mpc": self.mpc,
            "models": self.models,
            "anomalies": self.anomalies,
            "regime": self.regime,
            "twin_deltas": self.twin_deltas,
            "trust": self.trust,
            "fallback": self.fallback,
            "rewrites": self.rewrites,
            "wear": self.wear,
            "budget": self.budget,
        }


class OverseerEngineV3:
    """Paramount engine: model the machine, plan over horizons,
    replay alternatives, rewrite itself — all within hard safety walls."""

    def __init__(self, bus: Optional[EventBus] = None,
                 probe: Optional[HardwareProbe] = None,
                 horizon: int = 8):
        self._bus = bus
        self.probe = probe or HardwareProbe()
        self.governor = ResourceGovernor(probe=self.probe, bus=bus)
        self.base_budget = self.governor.base_budget
        self.enforcer = BudgetEnforcer()

        # V2 stack (retained as the sensing base)
        self.fusion = SensorFusion()
        self.forecaster = TrendForecaster()
        self.profiler = WorkloadProfiler()
        self.wear = WearModel()

        # V3 layers
        self.sysid = SystemIdentifier()
        self.mpc = ModelPredictiveController(horizon=horizon)
        self.twin = DigitalTwin()
        self.meta = MetaCognition()
        self.arbiter = QoSArbiter()

        self.setpoints = dict(V3_SETPOINTS)
        self._control = 1.0
        self._ticks = 0
        self._history: List[EngineV3Tick] = []
        self._stats = {"ticks": 0, "fallbacks": 0, "mpc_overrides": 0,
                       "anomaly_events": 0}

    # --- Consumer binding (same interface as V1/V2) ------------------------

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

    # --- The paramount tick ---------------------------------------------------

    def tick(self, demand: Optional[float] = None, events: float = 0.0) -> EngineV3Tick:
        self._ticks += 1
        self._stats["ticks"] += 1

        # 1. Raw sample + fusion
        hw = self.probe.read_state()
        fused = {
            "cpu": self.fusion.observe("cpu", hw.cpu_load),
            "memory": self.fusion.observe("memory", hw.memory_pressure),
            "thermal": self.fusion.observe("thermal", hw.thermal_max()),
            "battery": self.fusion.observe("battery", hw.battery_level if hw.battery_level is not None else 1.0),
            "io": self.fusion.observe("io", hw.io_wait),
        }
        states = {k: c.value for k, c in fused.items()}
        demand_signal = demand if demand is not None else states["cpu"]
        workload = self.profiler.observe(demand_signal, events)

        # 2. System identification: learn the machine's dynamics live
        for name, x in states.items():
            self.sysid.observe(name, x, self._control, demand_signal)
        models = {
            name: self.sysid.model(name)
            for name in states
            if self.sysid.model(name) is not None
        }

        # 3. Anomaly scan: model failure = root-cause signal
        anomalies = self.sysid.anomalies(threshold=3.0)
        if anomalies:
            self._stats["anomaly_events"] += 1

        # 4. MPC: receding-horizon optimization with hard walls
        mpc_result = self.mpc.plan(
            models={k: m for k, m in models.items() if m.samples >= 2},
            states=states,
            setpoints=self.setpoints,
            current_u=self._control,
            demand=demand_signal,
        )
        planned_control = mpc_result.control

        # 5. Digital twin: counterfactual grid over recent history
        cost_now = sum((states.get(ch, 0.0) - sp) ** 2 for ch, sp in self.setpoints.items())
        self.twin.record(states, self._control, demand_signal, cost_now)
        twin_grid = self.twin.grid_search(models, back_ticks=10, setpoints=self.setpoints) \
            if self._ticks % 3 == 0 and len(models) >= 2 else []
        best_delta = min((c.delta for c in twin_grid), default=0.0)
        if twin_grid:
            self.meta.observe_regret(max(0.0, -best_delta))

        # 6. Meta-cognition: scorecards + trust + bounded rewrites
        for ch, sp in self.setpoints.items():
            self.meta.observe_error(ch, states.get(ch, 0.0) - sp)
        trust = self.meta.trust()

        rewrites: List[Any] = []
        if self._ticks % 5 == 0:
            # Candidate rewrites: setpoint nudges within safety envelopes
            if "thermal" in self.setpoints:
                rw = self.meta.consider_rewrite(
                    "setpoints.thermal", self.setpoints["thermal"],
                    self.setpoints["thermal"] - 2.0,
                    "persistent regret on thermal channel",
                )
                if rw:
                    self.setpoints["thermal"] = rw.after
                    rewrites.append(rw)

        # 7. Trust gate: low trust → conservative fallback control
        fallback = trust < CONSERVATIVE_FLOOR
        if fallback:
            self._stats["fallbacks"] += 1
            applied_control = min(planned_control, 0.5)
        else:
            applied_control = planned_control
            if abs(planned_control - self._control) > 0.05:
                self._stats["mpc_overrides"] += 1
        self._control = applied_control

        # 8. Wear + budget enforcement
        self.wear.observe(states["thermal"], applied_control)
        budget = self.base_budget.scaled(applied_control)
        applied = self.enforcer.apply(budget)

        tick = EngineV3Tick(
            tick=self._ticks,
            control=applied_control,
            mpc=mpc_result.to_dict(),
            models=self.sysid.stats(),
            anomalies=anomalies,
            regime=workload.regime,
            twin_deltas=[c.to_dict() for c in twin_grid],
            trust=trust,
            fallback=fallback,
            rewrites=[r.to_dict() for r in rewrites],
            wear=self.wear.report().to_dict(),
            budget=budget.to_dict(),
        )
        self._history.append(tick)
        if len(self._history) > 64:
            self._history.pop(0)

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.engine_v3.tick",
                payload={
                    "control": applied_control,
                    "trajectory": mpc_result.trajectory_name,
                    "trust": trust,
                    "fallback": fallback,
                    "anomalies": anomalies,
                    "regime": workload.regime,
                    "applied": applied,
                },
                correlation_id=f"engine_v3_{self._ticks}",
            ))
        return tick

    # --- Surfaces -------------------------------------------------------------

    def tier_share(self, tier: str) -> float:
        pressure = 1.0 - self._control
        for alloc in self.arbiter.arbitrate(pressure):
            if alloc.tier == tier:
                return alloc.share
        return 0.0

    def status(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "device": self.governor.profile.to_dict(),
            "control": round(self._control, 4),
            "setpoints": {k: round(v, 3) for k, v in self.setpoints.items()},
            "sysid": self.sysid.stats(),
            "mpc": self.mpc.stats(),
            "twin": self.twin.stats(),
            "meta": self.meta.stats(),
            "wear": self.wear.report().to_dict(),
            "consumers": self.enforcer.consumers(),
        }

    def history(self, n: int = 10) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._history[-n:]]
