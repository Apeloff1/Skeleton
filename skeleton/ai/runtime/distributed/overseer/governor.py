"""
Skeleton Overseer — Resource Governor

The hardware-specialized engine at the heart of the Overseer: keeps
every system resource at optimal working levels on ANY device, reacting
to live hardware change in real time.

How it governs:

1. PROFILE  — the HardwareProbe classifies the device once (embedded /
   mobile / laptop / workstation / server) and derives a BudgetProfile:
   per-resource ceilings tuned to what this hardware can sustain.
2. SENSE    — live HardwareState + change events flow in every tick.
3. MODULATE — the governor computes per-resource throttle factors
   (0..1) from pressure, thermals, battery, and io-wait. These feed
   every resource consumer: LoadingQueue caps, backlog miner cadence,
   queue sizes, RAG plane widths, executor parallelism.
4. ACT      — apply budgets to consumers through BudgetEnforcer hooks;
   emergency actions on critical events (thermal crit, battery dying).
5. STABILIZE — hysteresis: budgets only shift when pressure moves past
   a deadband, preventing oscillation on noisy sensors.

The result: software demand always fits inside hardware budget,
regardless of device — and it degrades gracefully, never catastrophically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.overseer.hardware import (
    DeviceClass,
    HardwareChange,
    HardwareProbe,
    HardwareProfile,
    HardwareState,
)


@dataclass
class BudgetProfile:
    """Per-device resource ceilings derived from the hardware profile."""
    device_class: DeviceClass
    max_resident_planes: int
    max_in_flight_loads: int
    queue_size: int
    context_size: int
    executor_parallelism: int
    miner_interval_s: float
    rag_top_k: int
    history_window: int

    @staticmethod
    def for_device(profile: HardwareProfile) -> "BudgetProfile":
        cores = profile.cpu_cores
        mem_gb = profile.memory_total_mb / 1024.0
        cls = profile.device_class

        if cls == DeviceClass.EMBEDDED:
            return BudgetProfile(cls, max_resident_planes=1, max_in_flight_loads=1,
                                 queue_size=8, context_size=8, executor_parallelism=1,
                                 miner_interval_s=30.0, rag_top_k=3, history_window=16)
        if cls == DeviceClass.MOBILE:
            return BudgetProfile(cls, max_resident_planes=2, max_in_flight_loads=1,
                                 queue_size=16, context_size=16, executor_parallelism=2,
                                 miner_interval_s=15.0, rag_top_k=5, history_window=32)
        if cls == DeviceClass.LAPTOP:
            return BudgetProfile(cls, max_resident_planes=4, max_in_flight_loads=2,
                                 queue_size=32, context_size=32, executor_parallelism=min(4, cores),
                                 miner_interval_s=8.0, rag_top_k=8, history_window=64)
        if cls == DeviceClass.SERVER:
            return BudgetProfile(cls, max_resident_planes=12, max_in_flight_loads=6,
                                 queue_size=128, context_size=128,
                                 executor_parallelism=min(16, cores),
                                 miner_interval_s=2.0, rag_top_k=16, history_window=256)
        # WORKSTATION default
        return BudgetProfile(cls, max_resident_planes=6, max_in_flight_loads=3,
                             queue_size=64, context_size=64,
                             executor_parallelism=min(8, cores),
                             miner_interval_s=5.0, rag_top_k=12, history_window=128)

    def scaled(self, throttle: float) -> "BudgetProfile":
        """Return a copy with all numeric budgets scaled by throttle 0..1."""
        t = max(0.1, min(1.0, throttle))
        return BudgetProfile(
            self.device_class,
            max_resident_planes=max(1, int(self.max_resident_planes * t)),
            max_in_flight_loads=max(1, int(self.max_in_flight_loads * t)),
            queue_size=max(4, int(self.queue_size * t)),
            context_size=max(4, int(self.context_size * t)),
            executor_parallelism=max(1, int(self.executor_parallelism * t)),
            miner_interval_s=self.miner_interval_s / t,  # slower when throttled
            rag_top_k=max(2, int(self.rag_top_k * t)),
            history_window=max(8, int(self.history_window * t)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_class": self.device_class.value,
            "max_resident_planes": self.max_resident_planes,
            "max_in_flight_loads": self.max_in_flight_loads,
            "queue_size": self.queue_size,
            "context_size": self.context_size,
            "executor_parallelism": self.executor_parallelism,
            "miner_interval_s": round(self.miner_interval_s, 1),
            "rag_top_k": self.rag_top_k,
            "history_window": self.history_window,
        }


@dataclass
class ThrottleDecision:
    """One governor decision: the throttle vector + why."""
    throttle: float            # aggregate 0..1 (1 = full speed)
    per_resource: Dict[str, float]
    reasons: List[str]
    active_budget: BudgetProfile
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "throttle": round(self.throttle, 3),
            "per_resource": {k: round(v, 3) for k, v in self.per_resource.items()},
            "reasons": self.reasons,
            "budget": self.active_budget.to_dict(),
        }


class BudgetEnforcer:
    """Applies the active budget to resource consumers in the system."""

    def __init__(self):
        self._consumers: Dict[str, Callable[[BudgetProfile], None]] = {}

    def attach(self, name: str, apply_fn: Callable[[BudgetProfile], None]) -> None:
        """Attach a consumer with an apply callback (called on every budget change)."""
        self._consumers[name] = apply_fn

    def apply(self, budget: BudgetProfile) -> List[str]:
        applied = []
        for name, fn in self._consumers.items():
            try:
                fn(budget)
                applied.append(name)
            except Exception:
                continue
        return applied

    def consumers(self) -> List[str]:
        return sorted(self._consumers.keys())


class ResourceGovernor:
    """The hardware-specialized engine: keeps all system resources at
    optimal working levels, regardless of device."""

    DEADBAND = 0.05  # hysteresis: ignore pressure deltas below this

    def __init__(self, probe: Optional[HardwareProbe] = None,
                 bus: Optional[EventBus] = None):
        self.probe = probe or HardwareProbe()
        self._bus = bus
        self.profile = self.probe.profile()
        self.base_budget = BudgetProfile.for_device(self.profile)
        self.enforcer = BudgetEnforcer()
        self._active_throttle = 1.0
        self._last_decision: Optional[ThrottleDecision] = None
        self._history: List[ThrottleDecision] = []
        self._stats = {"ticks": 0, "throttle_changes": 0, "emergency_actions": 0,
                       "change_events": 0}

    # --- SENSE + MODULATE ------------------------------------------------------

    def _compute_throttles(self, state: HardwareState,
                            changes: List[HardwareChange]) -> Dict[str, float]:
        """Per-resource throttle factors from live hardware state."""
        throttles: Dict[str, float] = {}

        # CPU: back off as load climbs past 70%
        cpu_t = 1.0 if state.cpu_load < 0.7 else max(0.2, 1.0 - (state.cpu_load - 0.7) * 2.5)
        throttles["cpu"] = cpu_t

        # Memory: back off past 75% pressure, harder past 90%
        mp = state.memory_pressure
        mem_t = 1.0 if mp < 0.75 else (0.5 if mp < 0.9 else 0.2)
        throttles["memory"] = mem_t

        # Thermal: progressive backoff past 70C, floor at 85C
        tmax = state.thermal_max()
        if tmax <= 70:
            thermal_t = 1.0
        elif tmax <= 85:
            thermal_t = max(0.3, 1.0 - (tmax - 70) / 20.0)
        else:
            thermal_t = 0.15
        throttles["thermal"] = thermal_t

        # Battery: conserve when discharging low
        if state.battery_level is not None and not state.battery_charging:
            if state.battery_level <= 0.10:
                batt_t = 0.25
            elif state.battery_level <= 0.25:
                batt_t = 0.6
            else:
                batt_t = 0.9
        else:
            batt_t = 1.0
        throttles["battery"] = batt_t

        # IO: back off when the disk is the bottleneck
        io_t = 1.0 if state.io_wait < 0.2 else max(0.3, 1.0 - state.io_wait)
        throttles["io"] = io_t

        # Change events: take the harshest penalty on top
        for change in changes:
            if change.kind == "thermal_spike" and change.severity >= 1.0:
                throttles["thermal"] = min(throttles["thermal"], 0.1)
            elif change.kind == "battery_low":
                throttles["battery"] = min(throttles["battery"], 0.2)
            elif change.kind == "memory_pressure":
                throttles["memory"] = min(throttles["memory"], 0.2)
            elif change.kind == "cpu_spike":
                throttles["cpu"] = min(throttles["cpu"], 0.2)

        return throttles

    def tick(self) -> ThrottleDecision:
        """One governor cycle: sense → modulate → act → stabilize."""
        self._stats["ticks"] += 1
        state = self.probe.read_state()
        changes = self.probe.detect_changes(state)
        if changes:
            self._stats["change_events"] += len(changes)

        per_resource = self._compute_throttles(state, changes)
        aggregate = min(per_resource.values())
        reasons = [
            f"{name} at {value:.0%}"
            for name, value in per_resource.items()
            if value < 0.95
        ]

        # Hysteresis: only shift when the delta clears the deadband
        if abs(aggregate - self._active_throttle) < self.DEADBAND and self._last_decision is not None:
            return self._last_decision

        self._stats["throttle_changes"] += 1
        self._active_throttle = aggregate
        active_budget = self.base_budget.scaled(aggregate)

        decision = ThrottleDecision(
            throttle=aggregate,
            per_resource=per_resource,
            reasons=reasons,
            active_budget=active_budget,
        )
        self._last_decision = decision
        self._history.append(decision)
        if len(self._history) > 64:
            self._history.pop(0)

        # ACT: apply budgets to all attached consumers
        applied = self.enforcer.apply(active_budget)

        # Emergency actions on critical hardware events
        for change in changes:
            if change.severity >= 0.95:
                self._stats["emergency_actions"] += 1
                if self._bus:
                    self._bus.publish(DomainEvent(
                        topic="overseer.governor.emergency",
                        payload={"kind": change.kind, "detail": change.detail,
                                 "throttle": aggregate},
                    ))

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.governor.decision",
                payload={**decision.to_dict(), "applied": applied},
                correlation_id=f"governor_{self._stats['ticks']}",
            ))
        return decision

    # --- Introspection ------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "device": self.profile.to_dict(),
            "base_budget": self.base_budget.to_dict(),
            "active_throttle": round(self._active_throttle, 3),
            "last_decision": self._last_decision.to_dict() if self._last_decision else None,
            "consumers": self.enforcer.consumers(),
            **self._stats,
        }

    def history(self, n: int = 10) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._history[-n:]]
