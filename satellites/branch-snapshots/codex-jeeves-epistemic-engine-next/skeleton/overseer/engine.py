"""
Skeleton Overseer — Engine Core

The hardware-specialized Overseer as the main in-app engine: the
governor sits at the center of the four facet graphs and drives every
resource consumer in the organism through the BudgetEnforcer.

Loop:

    governor.tick()  → hardware state + throttle decision
    → LoadGraph gauges refresh (pressure now reflects device, not just queue)
    → BudgetEnforcer applies the scaled BudgetProfile to consumers:
        - LoadingQueue: resident cap + in-flight cap follow the budget
        - QueByPriority: queue size follows the budget
        - Backlog miner: interval follows the budget
        - AgenticRAG: top-k follows the budget
    → OverseerVerdict now carries device class + throttle + budget

The engine is device-agnostic: same code on a Raspberry Pi and a
64-core server — the probe classifies, the governor scales.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.overseer.governor import (
    BudgetEnforcer,
    BudgetProfile,
    ResourceGovernor,
    ThrottleDecision,
)
from skeleton.overseer.hardware import HardwareProbe, HardwareProfile, HardwareState
from skeleton.overseer.graphs import (
    FateGraph,
    FlowGraph,
    HealthGraph,
    LoadGraph,
    OverseerVerdict,
)


class OverseerEngine:
    """The main in-app engine: governor + facet graphs, unified."""

    def __init__(self, bus: Optional[EventBus] = None,
                 probe: Optional[HardwareProbe] = None):
        self._bus = bus
        self.governor = ResourceGovernor(probe=probe, bus=bus)
        self.flow = FlowGraph()
        self.health = HealthGraph()
        self.load = LoadGraph()
        self.fate = FateGraph()
        self._verdicts: List[OverseerVerdict] = []
        self._stats = {"engine_ticks": 0, "budget_applications": 0}

    # --- Consumer binding ---------------------------------------------------

    def bind_loader(self, loader: Any) -> None:
        """Bind a LoadingQueue: its caps follow the active budget."""
        def apply(budget: BudgetProfile) -> None:
            loader.max_resident = budget.max_resident_planes
            loader.max_in_flight = budget.max_in_flight_loads
        self.governor.enforcer.attach("loading_queue", apply)

    def bind_queue(self, queue: Any) -> None:
        """Bind a QueByPriority: its capacity follows the budget."""
        def apply(budget: BudgetProfile) -> None:
            queue.capacity_override = budget.queue_size
        self.governor.enforcer.attach("priority_queue", apply)

    def bind_miner(self, backlog: Any) -> None:
        """Bind the backlog miner: its cadence follows the budget."""
        def apply(budget: BudgetProfile) -> None:
            backlog.miner_interval = budget.miner_interval_s
        self.governor.enforcer.attach("backlog_miner", apply)

    def bind_rag(self, rag: Any) -> None:
        """Bind AgenticRAG: retrieval width follows the budget."""
        def apply(budget: BudgetProfile) -> None:
            rag.top_k_override = budget.rag_top_k
        self.governor.enforcer.attach("agentic_rag", apply)

    # --- Engine cycle --------------------------------------------------------

    def engine_tick(self) -> OverseerVerdict:
        """One full engine cycle: govern → gauge → verdict."""
        self._stats["engine_ticks"] += 1

        # 1. Governor: hardware-driven throttle decision
        decision = self.governor.tick()
        if self._last_applied(decision):
            self._stats["budget_applications"] += 1

        # 2. LoadGraph: pressure now reflects the device itself
        hw = decision.active_budget
        self.load.gauge("throttle", decision.throttle, capacity=1.0)
        self.load.gauge("resident_planes", float(hw.max_resident_planes),
                        capacity=float(self.governor.base_budget.max_resident_planes))

        # 3. Verdict with device context
        pressure = self.load.pressure()
        worst = self.health.worst()
        alignment = self.fate.alignment()
        anomalies: List[str] = list(decision.reasons)
        interventions: List[str] = []

        if decision.throttle <= 0.25:
            interventions.append("deep throttle active: defer non-critical work, slow miners")
        elif decision.throttle <= 0.6:
            interventions.append("moderate throttle: hold support planes lazy, narrow RAG")
        saturated = self.load.saturated()
        if saturated:
            anomalies.append(f"saturated: {', '.join(saturated[:3])}")
            interventions.append("evict idle planes via LoadingQueue")

        red_nodes = [nid for nid, state in worst if state == "red"]
        if decision.throttle <= 0.2 or red_nodes:
            state = "critical"
        elif decision.throttle <= 0.5 or pressure > 0.7:
            state = "strained"
        elif worst and worst[0][1] == "yellow":
            state = "stable"
        else:
            state = "thriving"

        verdict = OverseerVerdict(
            at=time.time(), state=state, pressure=pressure,
            worst_health=worst, fate_alignment=alignment,
            anomalies=anomalies, interventions=interventions,
        )
        self._verdicts.append(verdict)
        if len(self._verdicts) > 64:
            self._verdicts.pop(0)

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.engine.verdict",
                payload={**verdict.to_dict(),
                         "throttle": decision.throttle,
                         "device": self.governor.profile.device_class.value},
                correlation_id=f"engine_{self._stats['engine_ticks']}",
            ))
        return verdict

    def _last_applied(self, decision: ThrottleDecision) -> bool:
        """Did this decision actually shift the budget?"""
        return abs(decision.throttle - getattr(self, "_prev_throttle", 1.0)) > 0.01 and not setattr(self, "_prev_throttle", decision.throttle)

    # --- Surfaces -------------------------------------------------------------

    def device(self) -> Dict[str, Any]:
        """Full device report: profile + live state + budget."""
        return {
            "profile": self.governor.profile.to_dict(),
            "hardware": self.governor.probe.read_state().to_dict(),
            "budget": self.governor.base_budget.to_dict(),
            "active_throttle": round(self.governor._active_throttle, 3),
        }

    def equilibrium(self) -> Dict[str, Any]:
        """Hardware-software equilibrium: demand vs budget in one view."""
        return {
            "pressure": self.load.pressure(),
            "saturated": self.load.saturated(),
            "throttle": round(self.governor._active_throttle, 3),
            "gauges": {nid: n.attrs for nid, n in self.load.nodes.items()},
        }

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "governor": {
                "ticks": self.governor._stats["ticks"],
                "throttle_changes": self.governor._stats["throttle_changes"],
                "emergency_actions": self.governor._stats["emergency_actions"],
                "change_events": self.governor._stats["change_events"],
            },
            "graphs": {
                "flow": self.flow.summary(),
                "health": self.health.summary(),
                "load": self.load.summary(),
                "fate": self.fate.summary(),
            },
        }
