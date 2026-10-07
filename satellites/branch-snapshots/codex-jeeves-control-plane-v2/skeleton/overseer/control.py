"""
Skeleton Overseer — Control Core

High-intricacy regulation: multi-timescale control loops, PID-style
continuous regulation per resource, QoS-tiered budget arbitration,
and workload-aware setpoints. This replaces single-shot throttling
with a proper control system.

Architecture:

- FAST loop (every tick): PID regulators per resource channel
  (cpu, memory, thermal, battery, io) tracking dynamic setpoints.
  Each PID has anti-windup clamping and derivative-on-measurement
  to avoid setpoint-kick.
- SLOW loop (every N ticks): setpoint adaptation — targets shift with
  workload regime and forecasts (pre-throttle BEFORE thermal breach
  when the forecaster sees it coming).
- QoS arbitration: work is classed into four tiers
  (critical | interactive | background | deferrable). When the budget
  tightens, tiers shed in reverse order — deferrable first, critical
  never. Arbitration is weighted-fair, not binary.
- Regime-adaptive gains: PID gains scale per workload regime
  (burst → aggressive P, sustained → strong I, idle → relaxed).

All deterministic, stdlib-only, bounded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.overseer.predict import WorkloadRegime


# ---------------------------------------------------------------------------
# PID Regulator (per resource channel)
# ---------------------------------------------------------------------------

@dataclass
class PIDGains:
    kp: float = 1.2
    ki: float = 0.15
    kd: float = 0.05


class PIDRegulator:
    """PID with anti-windup and derivative-on-measurement.

    Output is a throttle factor 0..1 for the channel. Error is
    (setpoint - measured): positive error → full speed, negative →
    back off. The integral term closes steady-state offset slowly;
    the derivative damps fast rises (thermal spikes).
    """

    def __init__(self, name: str, setpoint: float, gains: Optional[PIDGains] = None):
        self.name = name
        self.setpoint = setpoint
        self.gains = gains or PIDGains()
        self._integral = 0.0
        self._prev_measurement: Optional[float] = None
        self._last_output = 1.0

    def update(self, measurement: float, dt: float = 1.0) -> float:
        error = self.setpoint - measurement

        # Integral with anti-windup clamping
        self._integral += error * dt * self.gains.ki
        self._integral = max(-0.5, min(0.5, self._integral))

        # Derivative on measurement (avoid setpoint kick)
        derivative = 0.0
        if self._prev_measurement is not None and dt > 0:
            derivative = -(measurement - self._prev_measurement) / dt * self.gains.kd
        self._prev_measurement = measurement

        raw = 1.0 + self.gains.kp * error + self._integral + derivative
        output = max(0.05, min(1.0, raw))
        self._last_output = output
        return output

    def set_gains(self, kp: float, ki: float, kd: float) -> None:
        self.gains = PIDGains(kp, ki, kd)

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_measurement = None


# ---------------------------------------------------------------------------
# QoS tiers + weighted-fair arbitration
# ---------------------------------------------------------------------------

class QoSTier:
    CRITICAL = "critical"        # user-facing, never shed
    INTERACTIVE = "interactive"  # conversation support
    BACKGROUND = "background"    # miners, consolidation
    DEFERRABLE = "deferrable"    # optional work, sheds first


TIER_WEIGHTS: Dict[str, float] = {
    QoSTier.CRITICAL: 1.0,
    QoSTier.INTERACTIVE: 0.7,
    QoSTier.BACKGROUND: 0.35,
    QoSTier.DEFERRABLE: 0.15,
}


@dataclass
class TierAllocation:
    """One tier's share of the budget under current pressure."""
    tier: str
    share: float        # 0..1 of total budget
    allowed: bool       # tier permitted at all under this pressure
    effective_weight: float

    def to_dict(self) -> Dict[str, Any]:
        return {"tier": self.tier, "share": round(self.share, 3),
                "allowed": self.allowed, "weight": round(self.effective_weight, 3)}


class QoSArbiter:
    """Weighted-fair budget arbitration across QoS tiers.

    Under pressure p (0 = relaxed, 1 = max pressure), tiers shed in
    reverse order of weight: deferrable cut first, background next,
    interactive throttled but running, critical untouched.
    """

    SHED_THRESHOLDS: Dict[str, float] = {
        QoSTier.DEFERRABLE: 0.55,
        QoSTier.BACKGROUND: 0.75,
        QoSTier.INTERACTIVE: 0.92,
        QoSTier.CRITICAL: 1.01,  # never shed
    }

    def arbitrate(self, pressure: float) -> List[TierAllocation]:
        allocations: List[TierAllocation] = []
        for tier, weight in TIER_WEIGHTS.items():
            allowed = pressure < self.SHED_THRESHOLDS[tier]
            # Effective weight decays smoothly as pressure approaches the shed point
            headroom = self.SHED_THRESHOLDS[tier] - pressure
            effective = weight * max(0.0, min(1.0, headroom / 0.3)) if allowed else 0.0
            allocations.append(TierAllocation(
                tier=tier, share=0.0, allowed=allowed, effective_weight=effective,
            ))
        total = sum(a.effective_weight for a in allocations)
        if total > 0:
            for a in allocations:
                a.share = a.effective_weight / total
        return allocations

    def tier_budget(self, pressure: float, tier: str, base: float) -> float:
        """Absolute budget for one tier under pressure."""
        for alloc in self.arbitrate(pressure):
            if alloc.tier == tier:
                return base * alloc.share * (TIER_WEIGHTS[tier] / max(TIER_WEIGHTS.values()))
        return 0.0


# ---------------------------------------------------------------------------
# Multi-timescale control core
# ---------------------------------------------------------------------------

# Regime-adaptive PID gains: (kp, ki, kd) per workload regime
REGIME_GAINS: Dict[str, PIDGains] = {
    WorkloadRegime.IDLE: PIDGains(0.8, 0.05, 0.02),
    WorkloadRegime.INTERACTIVE: PIDGains(1.2, 0.15, 0.05),
    WorkloadRegime.BATCH: PIDGains(1.4, 0.2, 0.03),
    WorkloadRegime.BURST: PIDGains(2.0, 0.08, 0.12),
    WorkloadRegime.SUSTAINED: PIDGains(1.0, 0.3, 0.02),
}

# Base setpoints per channel (fraction of safe operating envelope)
BASE_SETPOINTS: Dict[str, float] = {
    "cpu": 0.75,
    "memory": 0.70,
    "thermal": 68.0,   # °C
    "battery": 0.30,   # keep 30% reserve when mobile
    "io": 0.15,
}


@dataclass
class ControlDecision:
    """One fast-loop output: channel outputs + arbitration + meta."""
    channel_outputs: Dict[str, float]
    aggregate: float
    allocations: List[TierAllocation]
    regime: str
    setpoints: Dict[str, float]
    anticipatory: List[str]  # pre-emptive actions from forecasts
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aggregate": round(self.aggregate, 3),
            "channels": {k: round(v, 3) for k, v in self.channel_outputs.items()},
            "allocations": [a.to_dict() for a in self.allocations],
            "regime": self.regime,
            "setpoints": {k: round(v, 3) for k, v in self.setpoints.items()},
            "anticipatory": self.anticipatory,
        }


class ControlCore:
    """Multi-timescale control: fast PID loops + slow setpoint adaptation
    + QoS arbitration, regime-adaptive gains, forecast-driven pre-throttle."""

    SLOW_LOOP_EVERY = 5  # ticks

    def __init__(self):
        self._regulators: Dict[str, PIDRegulator] = {
            name: PIDRegulator(name, sp) for name, sp in BASE_SETPOINTS.items()
        }
        self._arbiter = QoSArbiter()
        self._setpoints = dict(BASE_SETPOINTS)
        self._ticks = 0
        self._regime = WorkloadRegime.IDLE
        self._stats = {"fast_ticks": 0, "slow_ticks": 0, "anticipations": 0}

    def fast_tick(self, measurements: Dict[str, float],
                  workload: Any, forecasts: Optional[Dict[str, Any]] = None) -> ControlDecision:
        """FAST loop: one control pass over fused measurements."""
        self._ticks += 1
        self._stats["fast_ticks"] += 1
        self._regime = workload.regime

        # Regime-adaptive gains
        gains = REGIME_GAINS.get(workload.regime, REGIME_GAINS[WorkloadRegime.INTERACTIVE])
        for reg in self._regulators.values():
            reg.set_gains(gains.kp, gains.ki, gains.kd)

        # Slow loop: adapt setpoints from forecasts
        anticipatory: List[str] = []
        if self._ticks % self.SLOW_LOOP_EVERY == 0:
            self._stats["slow_ticks"] += 1
            anticipatory = self._slow_tick(measurements, forecasts or {})

        # PID update per channel
        outputs: Dict[str, float] = {}
        for name, regulator in self._regulators.items():
            measurement = measurements.get(name)
            if measurement is None:
                outputs[name] = 1.0
                continue
            regulator.setpoint = self._setpoints[name]
            outputs[name] = regulator.update(measurement)

        aggregate = min(outputs.values()) if outputs else 1.0
        pressure = 1.0 - aggregate
        allocations = self._arbiter.arbitrate(pressure)

        return ControlDecision(
            channel_outputs=outputs,
            aggregate=aggregate,
            allocations=allocations,
            regime=workload.regime,
            setpoints=dict(self._setpoints),
            anticipatory=anticipatory,
        )

    def _slow_tick(self, measurements: Dict[str, float],
                   forecasts: Dict[str, Any]) -> List[str]:
        """SLOW loop: shift setpoints using forecasts — pre-throttle."""
        actions: List[str] = []

        thermal_fc = forecasts.get("thermal")
        if thermal_fc is not None and thermal_fc.crosses_threshold_at is not None:
            steps = thermal_fc.crosses_threshold_at
            if steps <= 10:
                # Tighten the thermal setpoint BEFORE the breach arrives
                self._setpoints["thermal"] = max(60.0, BASE_SETPOINTS["thermal"] - 5.0)
                actions.append(f"pre-throttling thermal (breach in ~{steps} steps)")
                self._stats["anticipations"] += 1
        else:
            # Relax back toward base when the forecast clears
            if self._setpoints["thermal"] < BASE_SETPOINTS["thermal"]:
                self._setpoints["thermal"] = min(
                    BASE_SETPOINTS["thermal"], self._setpoints["thermal"] + 1.0)

        mem_fc = forecasts.get("memory")
        if mem_fc is not None and mem_fc.crosses_threshold_at is not None:
            if mem_fc.crosses_threshold_at <= 10:
                self._setpoints["memory"] = max(0.55, BASE_SETPOINTS["memory"] - 0.08)
                actions.append(f"pre-throttling memory (breach in ~{mem_fc.crosses_threshold_at} steps)")
                self._stats["anticipations"] += 1

        # Regime-driven setpoint shaping
        if self._regime == WorkloadRegime.IDLE:
            self._setpoints["cpu"] = 0.85  # let the machine idle freely
        elif self._regime == WorkloadRegime.SUSTAINED:
            self._setpoints["cpu"] = 0.70  # protect against thermal soak
        else:
            self._setpoints["cpu"] = BASE_SETPOINTS["cpu"]

        return actions

    def stats(self) -> Dict[str, Any]:
        return {**self._stats,
                "setpoints": {k: round(v, 3) for k, v in self._setpoints.items()},
                "regime": self._regime}
