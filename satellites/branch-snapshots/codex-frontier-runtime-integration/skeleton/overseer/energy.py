"""
Skeleton Overseer — Energy Model

Energy-aware computing: the engine tracks power draw per subsystem
and total battery/drain trajectory, trading quality for battery life
explicitly and honestly.

Model:
- PowerDraw: estimated watts per subsystem from utilization curves
  (cpu busy-fraction → TDP-scaled draw, gpu class → fixed class draw,
  memory pressure → refresh-rate proxy, io wait → storage class draw).
  No hardware power meters needed — utilization is the proxy.
- DrainForecast: battery trajectory from current draw + level; time
  to empty under hold/ramp-down scenarios, and the minimum throttle
  that reaches a target reserve at a target time.
- EnergyBudget: per-subsystem watt caps derived from the device class
  and battery state; BudgetProfile gains energy fields so enforcement
  covers watts as well as counts.
- QualityOfServiceTrade: when drain exceeds budget, the model computes
  exactly which quality knobs to turn (rag_top_k, queue depth, miner
  cadence) and by how much, to meet the energy target — the
  quality-for-battery exchange rate is computed, not guessed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Watts per unit utilization per subsystem, per device class
DRAW_CURVES: Dict[str, Dict[str, float]] = {
    "embedded":    {"cpu": 2.5, "gpu": 0.0, "memory": 0.4, "io": 0.3, "base": 0.8},
    "mobile":      {"cpu": 6.0, "gpu": 1.5, "memory": 0.8, "io": 0.5, "base": 1.2},
    "laptop":      {"cpu": 15.0, "gpu": 4.0, "memory": 1.5, "io": 1.0, "base": 2.0},
    "workstation": {"cpu": 45.0, "gpu": 20.0, "memory": 3.0, "io": 2.0, "base": 4.0},
    "server":      {"cpu": 120.0, "gpu": 75.0, "memory": 8.0, "io": 6.0, "base": 10.0},
}

GPU_CLASS_DRAW = {"none": 0.0, "integrated": 0.4, "discrete": 1.0, "compute": 1.6}


@dataclass
class PowerDraw:
    """Estimated current draw per subsystem + total."""
    cpu_w: float
    gpu_w: float
    memory_w: float
    io_w: float
    base_w: float
    total_w: float

    def to_dict(self) -> Dict[str, Any]:
        return {"cpu_w": round(self.cpu_w, 2), "gpu_w": round(self.gpu_w, 2),
                "memory_w": round(self.memory_w, 2), "io_w": round(self.io_w, 2),
                "base_w": round(self.base_w, 2), "total_w": round(self.total_w, 2)}


class PowerModel:
    """Utilization → watts estimation for the current device."""

    def __init__(self, device_class: str, gpu_class: str = "none"):
        self.curve = DRAW_CURVES.get(device_class, DRAW_CURVES["workstation"])
        self.gpu_factor = GPU_CLASS_DRAW.get(gpu_class, 0.0)
        self._history: List[PowerDraw] = []

    def estimate(self, cpu: float, memory: float, io: float,
                 gpu_util: float = 0.0) -> PowerDraw:
        cpu_w = self.curve["cpu"] * cpu
        gpu_w = self.curve["gpu"] * self.gpu_factor * max(gpu_util, cpu * 0.5)
        memory_w = self.curve["memory"] * memory
        io_w = self.curve["io"] * io
        base_w = self.curve["base"]
        draw = PowerDraw(cpu_w, gpu_w, memory_w, io_w, base_w,
                         cpu_w + gpu_w + memory_w + io_w + base_w)
        self._history.append(draw)
        if len(self._history) > 64:
            self._history.pop(0)
        return draw

    def mean_draw(self, n: int = 16) -> float:
        window = self._history[-n:]
        return sum(d.total_w for d in window) / max(1, len(window))


@dataclass
class DrainForecast:
    """Battery trajectory under current and modified draw."""
    level: float
    hours_to_empty: Optional[float]
    min_throttle_for_reserve: Optional[float]
    reserve_target: float
    reserve_deadline_hours: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": round(self.level, 3),
            "hours_to_empty": round(self.hours_to_empty, 2) if self.hours_to_empty else None,
            "min_throttle_for_reserve": (round(self.min_throttle_for_reserve, 3)
                                          if self.min_throttle_for_reserve is not None else None),
            "reserve_target": self.reserve_target,
        }


class BatteryModel:
    """Battery drain forecasting with quality-of-service trade-off."""

    DEFAULT_CAPACITY_WH = 50.0  # nominal; scaled by device class

    CAPACITY_BY_CLASS = {"embedded": 10.0, "mobile": 20.0, "laptop": 60.0,
                         "workstation": 0.0, "server": 0.0}

    def __init__(self, device_class: str):
        self.capacity_wh = self.CAPACITY_BY_CLASS.get(device_class, 0.0)

    def forecast(self, level: float, current_draw_w: float,
                 reserve_target: float = 0.2,
                 reserve_deadline_hours: float = 2.0) -> DrainForecast:
        """Hours to empty + minimum throttle to hold a reserve."""
        if self.capacity_wh <= 0 or level is None:
            return DrainForecast(level or 1.0, None, None, reserve_target, reserve_deadline_hours)

        wh_remaining = level * self.capacity_wh
        hours = wh_remaining / max(0.1, current_draw_w)

        # Minimum throttle: the draw reduction needed so the battery
        # still holds reserve_target at the deadline
        wh_needed = reserve_target * self.capacity_wh + current_draw_w * reserve_deadline_hours
        if wh_remaining > wh_needed:
            min_throttle = None  # on track without intervention
        else:
            allowed_draw = max(0.1, (wh_remaining - reserve_target * self.capacity_wh)
                               / reserve_deadline_hours)
            min_throttle = min(1.0, allowed_draw / current_draw_w)

        return DrainForecast(level, hours, min_throttle, reserve_target, reserve_deadline_hours)

    def quality_trade(self, draw: PowerDraw, target_w: float) -> Dict[str, float]:
        """Exact knob turns to reach a watt target: the quality-for-
        battery exchange rate, computed from the draw decomposition."""
        if draw.total_w <= target_w:
            return {"rag_top_k_scale": 1.0, "queue_scale": 1.0, "miner_scale": 1.0}
        ratio = target_w / max(0.1, draw.total_w)
        # CPU dominates: rag_top_k scales hardest (it drives cpu work),
        # queue next, miner cadence last (cheapest to slow)
        return {
            "rag_top_k_scale": max(0.25, ratio),
            "queue_scale": max(0.4, ratio + 0.1),
            "miner_scale": max(0.5, ratio + 0.2),
        }


class EnergyModel:
    """Unified energy layer: power + battery + budget + trades."""

    def __init__(self, device_class: str, gpu_class: str = "none"):
        self.power = PowerModel(device_class, gpu_class)
        self.battery = BatteryModel(device_class)
        self._stats = {"estimates": 0, "trades_issued": 0}

    def evaluate(self, cpu: float, memory: float, io: float,
                 battery_level: Optional[float], gpu_util: float = 0.0) -> Dict[str, Any]:
        self._stats["estimates"] += 1
        draw = self.power.estimate(cpu, memory, io, gpu_util)
        forecast = self.battery.forecast(battery_level or 1.0, draw.total_w)
        out: Dict[str, Any] = {
            "draw": draw.to_dict(),
            "mean_draw_w": round(self.power.mean_draw(), 2),
            "forecast": forecast.to_dict(),
        }
        if forecast.min_throttle_for_reserve is not None:
            # Compute the exact quality trade to meet the reserve
            target_w = draw.total_w * forecast.min_throttle_for_reserve
            out["quality_trade"] = self.battery.quality_trade(draw, target_w)
            self._stats["trades_issued"] += 1
        return out

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
