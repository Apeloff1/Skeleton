"""Forecaster — time-series prediction for capacity and anomaly planning.

Forecasts metric trajectories (latency, queue depth, error rate,
resource usage) using Holt linear exponential smoothing with optional
damped trend. Produces point forecasts with confidence intervals and
predicts time-to-threshold for capacity alerts ("queue full in ~4h").
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ForecastPoint:
    step: int
    value: float
    lower: float
    upper: float



def _unit(name: str, value: float, *, allow_zero: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if allow_zero:
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
    elif not 0.0 < number <= 1.0:
        raise ValueError(f"{name} must be in (0, 1]")
    return number


class Forecaster:
    """Holt double-exponential-smoothing forecaster."""

    def __init__(self, alpha: float = 0.4, beta: float = 0.1, damping: float = 0.9):
        self.alpha = _unit("alpha", alpha, allow_zero=False)
        self.beta = _unit("beta", beta, allow_zero=False)
        self.damping = _unit("damping", damping, allow_zero=True)
        self._series: Dict[str, List[float]] = {}

    def feed(self, metric: str, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("metric value must be finite")
        buf = self._series.setdefault(metric, [])
        buf.append(float(value))
        if len(buf) > 500:
            buf.pop(0)

    def _holt(self, values: List[float], steps: int) -> Dict[str, Any]:
        if len(values) < 3:
            return {"error": "insufficient data", "samples": len(values)}
        level = values[0]
        trend = values[1] - values[0]
        residuals: List[float] = []
        for v in values[1:]:
            last_level = level
            level = self.alpha * v + (1 - self.alpha) * (level + self.damping * trend)
            trend = self.beta * (level - last_level) + (1 - self.beta) * self.damping * trend
            residuals.append(v - level)
        std = math.sqrt(sum(r ** 2 for r in residuals) / max(1, len(residuals))) if residuals else 0.0
        points: List[ForecastPoint] = []
        damped_trend = trend
        for h in range(1, steps + 1):
            forecast = level + damped_trend
            margin = 1.96 * std * math.sqrt(h)
            points.append(ForecastPoint(step=h, value=forecast, lower=forecast - margin, upper=forecast + margin))
            damped_trend *= self.damping
        return {
            "level": round(level, 4),
            "trend": round(trend, 4),
            "residual_std": round(std, 4),
            "forecast": [{"step": p.step, "value": round(p.value, 4), "lower": round(p.lower, 4), "upper": round(p.upper, 4)} for p in points],
        }

    def forecast(self, metric: str, steps: int = 10) -> Dict[str, Any]:
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
            raise ValueError("steps must be a positive integer")
        values = self._series.get(metric, [])
        result = self._holt(values, steps)
        result["metric"] = metric
        result["samples"] = len(values)
        return result

    def time_to_threshold(self, metric: str, threshold: float) -> Dict[str, Any]:
        values = self._series.get(metric, [])
        if len(values) < 3:
            return {"metric": metric, "crosses": False, "reason": "insufficient data"}
        result = self._holt(values, 100)
        if "error" in result:
            return {"metric": metric, "crosses": False, **result}
        current = values[-1]
        for point in result["forecast"]:
            if (current < threshold and point["value"] >= threshold) or (current > threshold and point["value"] <= threshold):
                return {"metric": metric, "crosses": True, "steps": point["step"], "threshold": threshold, "current": round(current, 4)}
        return {"metric": metric, "crosses": False, "threshold": threshold, "current": round(current, 4), "trend": result["trend"]}

    def anomalies_foreseen(self, metric: str, zscore: float = 3.0) -> List[Dict[str, Any]]:
        result = self.forecast(metric, steps=10)
        if "error" in result:
            return []
        return [p for p in result["forecast"] if p["lower"] < 0 < p["upper"] and abs(p["value"]) > zscore * result.get("residual_std", 1)]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "forecaster-card",
            "metrics": {m: len(v) for m, v in self._series.items()},
            "params": {"alpha": self.alpha, "beta": self.beta, "damping": self.damping},
        }
