"""
Skeleton Overseer — Predictive Layer

High-intricacy sensing: instead of reacting to the latest sample,
the engine fuses noisy sensors, forecasts their trajectories, and
profiles the workload driving them. Control becomes anticipatory.

Components:

- SensorFusion: exponential-filter + outlier rejection per channel,
  with confidence weighting (recent variance → channel confidence)
- TrendForecaster: Holt double-exponential smoothing per channel —
  level + trend — yielding k-step-ahead forecasts with widening
  uncertainty bands
- WorkloadProfiler: classifies the current workload regime
  (idle | interactive | batch | burst | sustained) from the shape of
  recent demand, with dwell-time hysteresis so regimes don't flap
- WearModel: cumulative thermal-time integral and throttle-duty
  estimate — long-horizon hardware stress bookkeeping

Everything is deterministic, stdlib-only, and bounded-memory.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Sensor Fusion
# ---------------------------------------------------------------------------

@dataclass
class FusedChannel:
    """One fused sensor channel: value, confidence, variance."""
    name: str
    value: float
    confidence: float
    variance: float
    samples: int


class SensorFusion:
    """EMA smoothing with MAD outlier rejection per channel.

    Each sample updates an exponential moving mean/variance; samples
    beyond k·MAD are clipped before fusion. Channel confidence is
    derived from recent variance — stable sensors score high.
    """

    def __init__(self, alpha: float = 0.3, outlier_k: float = 3.0, window: int = 32):
        self.alpha = alpha
        self.outlier_k = outlier_k
        self.window = window
        self._channels: Dict[str, Dict[str, Any]] = {}

    def observe(self, name: str, value: float) -> FusedChannel:
        ch = self._channels.setdefault(name, {
            "mean": value, "var": 0.0, "samples": [], "n": 0,
        })
        # Outlier rejection via median absolute deviation
        samples = ch["samples"]
        if len(samples) >= 5:
            med = sorted(samples)[len(samples) // 2]
            mad = sorted(abs(s - med) for s in samples)[len(samples) // 2] or 1e-6
            if abs(value - med) > self.outlier_k * mad * 1.4826:
                value = med + math.copysign(self.outlier_k * mad * 1.4826, value - med)

        prev = ch["mean"]
        ch["mean"] = self.alpha * value + (1 - self.alpha) * prev
        ch["var"] = self.alpha * (value - prev) ** 2 + (1 - self.alpha) * ch["var"]
        samples.append(value)
        if len(samples) > self.window:
            samples.pop(0)
        ch["n"] += 1

        confidence = 1.0 / (1.0 + math.sqrt(ch["var"]) * 10.0)
        return FusedChannel(name=name, value=ch["mean"], confidence=round(confidence, 3),
                            variance=ch["var"], samples=ch["n"])

    def channels(self) -> Dict[str, FusedChannel]:
        return {
            name: FusedChannel(name, ch["mean"], round(1.0 / (1.0 + math.sqrt(ch["var"]) * 10.0), 3),
                               ch["var"], ch["n"])
            for name, ch in self._channels.items()
        }


# ---------------------------------------------------------------------------
# Trend Forecaster (Holt double-exponential smoothing)
# ---------------------------------------------------------------------------

@dataclass
class Forecast:
    """k-step-ahead forecast with uncertainty band."""
    channel: str
    horizon_steps: int
    point: float
    lower: float
    upper: float
    trend_per_step: float
    crosses_threshold_at: Optional[int]  # steps until threshold breach, None if never

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "horizon": self.horizon_steps,
            "point": round(self.point, 4),
            "band": [round(self.lower, 4), round(self.upper, 4)],
            "trend": round(self.trend_per_step, 5),
            "breach_in": self.crosses_threshold_at,
        }


class TrendForecaster:
    """Holt's linear trend per channel with breach prediction."""

    def __init__(self, alpha: float = 0.4, beta: float = 0.1):
        self.alpha = alpha
        self.beta = beta
        self._level: Dict[str, float] = {}
        self._trend: Dict[str, float] = {}
        self._resid_var: Dict[str, float] = {}

    def observe(self, name: str, value: float) -> None:
        if name not in self._level:
            self._level[name] = value
            self._trend[name] = 0.0
            self._resid_var[name] = 0.0
            return
        level_prev = self._level[name]
        self._level[name] = self.alpha * value + (1 - self.alpha) * (level_prev + self._trend[name])
        self._trend[name] = self.beta * (self._level[name] - level_prev) + (1 - self.beta) * self._trend[name]
        resid = value - self._level[name]
        self._resid_var[name] = 0.3 * resid ** 2 + 0.7 * self._resid_var[name]

    def forecast(self, name: str, steps: int = 5,
                 threshold: Optional[float] = None) -> Optional[Forecast]:
        if name not in self._level:
            return None
        point = self._level[name] + self._trend[name] * steps
        sigma = math.sqrt(self._resid_var[name]) * math.sqrt(steps)  # widening band
        breach = None
        if threshold is not None and self._trend[name] != 0:
            # Steps until the point estimate crosses the threshold
            if (self._trend[name] > 0 and point >= threshold) or \
               (self._trend[name] < 0 and point <= threshold):
                remaining = (threshold - self._level[name]) / self._trend[name]
                breach = max(0, int(remaining)) if remaining > 0 else 0
        return Forecast(
            channel=name, horizon_steps=steps, point=point,
            lower=point - 2 * sigma, upper=point + 2 * sigma,
            trend_per_step=self._trend[name],
            crosses_threshold_at=breach,
        )

    def trends(self) -> Dict[str, float]:
        return dict(self._trend)


# ---------------------------------------------------------------------------
# Workload Profiler
# ---------------------------------------------------------------------------

class WorkloadRegime:
    IDLE = "idle"
    INTERACTIVE = "interactive"
    BATCH = "batch"
    BURST = "burst"
    SUSTAINED = "sustained"


@dataclass
class WorkloadProfile:
    """Current workload regime with dwell and demand stats."""
    regime: str
    dwell_ticks: int
    demand_mean: float
    demand_variance: float
    event_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime,
            "dwell_ticks": self.dwell_ticks,
            "demand_mean": round(self.demand_mean, 3),
            "demand_variance": round(self.demand_variance, 4),
            "event_rate": round(self.event_rate, 3),
        }


class WorkloadProfiler:
    """Classifies the workload regime from demand shape, with
    dwell-time hysteresis (must dwell N ticks before switching)."""

    DWELL_MIN = 3

    def __init__(self, window: int = 32):
        self.window = window
        self._demands: List[float] = []
        self._events: List[float] = []
        self._regime = WorkloadRegime.IDLE
        self._candidate: Optional[str] = None
        self._candidate_ticks = 0
        self._dwell = 0

    def observe(self, demand: float, events: float = 0.0) -> WorkloadProfile:
        self._demands.append(demand)
        self._events.append(events)
        if len(self._demands) > self.window:
            self._demands.pop(0)
            self._events.pop(0)

        mean = sum(self._demands) / len(self._demands)
        var = sum((d - mean) ** 2 for d in self._demands) / len(self._demands)
        event_rate = sum(self._events) / max(1, len(self._events))

        # Regime classification from demand shape
        if mean < 0.05 and event_rate < 0.05:
            proposed = WorkloadRegime.IDLE
        elif var > 0.15 and mean < 0.5:
            proposed = WorkloadRegime.BURST
        elif mean > 0.75 and var < 0.05:
            proposed = WorkloadRegime.SUSTAINED
        elif mean > 0.5:
            proposed = WorkloadRegime.BATCH
        else:
            proposed = WorkloadRegime.INTERACTIVE

        # Dwell-time hysteresis
        if proposed == self._regime:
            self._dwell += 1
            self._candidate = None
            self._candidate_ticks = 0
        else:
            if proposed == self._candidate:
                self._candidate_ticks += 1
            else:
                self._candidate = proposed
                self._candidate_ticks = 1
            if self._candidate_ticks >= self.DWELL_MIN:
                self._regime = proposed
                self._dwell = 1
                self._candidate = None
                self._candidate_ticks = 0

        return WorkloadProfile(
            regime=self._regime, dwell_ticks=self._dwell,
            demand_mean=mean, demand_variance=var, event_rate=event_rate,
        )


# ---------------------------------------------------------------------------
# Wear Model
# ---------------------------------------------------------------------------

@dataclass
class WearReport:
    """Long-horizon hardware stress bookkeeping."""
    thermal_time_integral: float   # °C·hours above 60°C
    throttle_duty: float           # fraction of time throttled below 0.8
    deep_throttle_events: int
    estimated_wear_index: float    # 0..1 composite

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thermal_time_c_hours": round(self.thermal_time_integral, 3),
            "throttle_duty": round(self.throttle_duty, 3),
            "deep_throttle_events": self.deep_throttle_events,
            "wear_index": round(self.estimated_wear_index, 4),
        }


class WearModel:
    """Cumulative hardware stress: thermal-time integral + throttle duty."""

    THERMAL_FLOOR_C = 60.0

    def __init__(self):
        self._thermal_integral = 0.0
        self._throttled_ticks = 0
        self._total_ticks = 0
        self._deep_events = 0
        self._last_ts: Optional[float] = None

    def observe(self, temp_max_c: float, throttle: float) -> None:
        now = time.time()
        if self._last_ts is not None and temp_max_c > self.THERMAL_FLOOR_C:
            hours = (now - self._last_ts) / 3600.0
            self._thermal_integral += (temp_max_c - self.THERMAL_FLOOR_C) * hours
        self._last_ts = now
        self._total_ticks += 1
        if throttle < 0.8:
            self._throttled_ticks += 1
        if throttle <= 0.25:
            self._deep_events += 1

    def report(self) -> WearReport:
        duty = self._throttled_ticks / max(1, self._total_ticks)
        wear = min(1.0, self._thermal_integral / 100.0 + duty * 0.5 + self._deep_events * 0.01)
        return WearReport(
            thermal_time_integral=self._thermal_integral,
            throttle_duty=duty,
            deep_throttle_events=self._deep_events,
            estimated_wear_index=wear,
        )
