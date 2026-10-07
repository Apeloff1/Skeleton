"""
Skeleton Observability — Metrics, tracing, and anomaly detection

Provides:
- Sampler: Adaptive sampling for telemetry
- MetricsCollector: Counter, gauge, histogram aggregation
- AnomalyDetector: Statistical anomaly detection on event streams
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class MetricPoint:
    """A single metric observation."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)


class Sampler:
    """Adaptive sampling for telemetry data."""

    def __init__(self, base_rate: float = 0.1, max_rate: float = 1.0):
        self.base_rate = base_rate
        self.max_rate = max_rate
        self._current_rate = base_rate
        self._error_count = 0
        self._total = 0

    def should_sample(self) -> bool:
        import random
        return random.random() < self._current_rate

    def record_error(self) -> None:
        self._error_count += 1
        self._current_rate = min(self.max_rate, self._current_rate * 1.5)

    def record_success(self) -> None:
        self._total += 1
        self._current_rate = max(self.base_rate, self._current_rate * 0.95)

    def stats(self) -> Dict[str, Any]:
        return {
            "rate": self._current_rate,
            "errors": self._error_count,
            "total": self._total,
        }


def default_sampler() -> Sampler:
    return Sampler(base_rate=0.1)


class MetricsCollector:
    """Counter, gauge, and histogram aggregation."""

    def __init__(self, retention_seconds: int = 86400):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, Deque[MetricPoint]] = {}
        self._retention = retention_seconds

    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        self._gauges[key] = value

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = deque(maxlen=10000)
        self._histograms[key].append(MetricPoint(name=name, value=value, labels=labels or {}))

    def snapshot(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }
        for key, points in self._histograms.items():
            values = [p.value for p in points]
            if values:
                result["histograms"][key] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": statistics.mean(values),
                    "p50": statistics.median(values),
                    "p99": sorted(values)[int(len(values) * 0.99)] if len(values) > 1 else values[0],
                }
        return result

    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


class AnomalyDetector:
    """Statistical anomaly detection on event streams."""

    def __init__(self, bus: Optional[EventBus] = None, window_size: int = 100):
        self._bus = bus
        self._window_size = window_size
        self._values: Deque[float] = deque(maxlen=window_size)
        self._threshold_multiplier = 3.0

    def observe(self, value: float) -> Optional[str]:
        """Observe a value, return alert if anomalous."""
        if len(self._values) < 10:
            self._values.append(value)
            return None
        
        mean = statistics.mean(self._values)
        try:
            stdev = statistics.stdev(self._values)
        except statistics.StatisticsError:
            stdev = 0
        
        self._values.append(value)
        
        if stdev > 0 and abs(value - mean) > self._threshold_multiplier * stdev:
            alert = f"Anomaly detected: {value:.2f} (mean={mean:.2f}, std={stdev:.2f})"
            if self._bus:
                self._bus.emit("observability.anomaly", {
                    "value": value,
                    "mean": mean,
                    "stdev": stdev,
                    "threshold": self._threshold_multiplier,
                })
            return alert
        
        return None

    def stats(self) -> Dict[str, Any]:
        return {
            "observations": len(self._values),
            "window_size": self._window_size,
            "threshold": self._threshold_multiplier,
        }
