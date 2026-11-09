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
    """Counter, gauge, and histogram aggregation.

    Java acceleration is deliberately opt-in. When enabled, only histogram
    snapshot math is offloaded, and only once the batch is large enough to
    amortize process/protocol overhead. Counters, gauges, storage, labels, and
    the public snapshot shape remain Python-owned.
    """

    def __init__(
        self,
        retention_seconds: int = 86400,
        *,
        use_jvm_acceleration: bool = False,
        accelerator: Any = None,
    ):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, Deque[MetricPoint]] = {}
        self._retention = retention_seconds
        self._use_jvm_acceleration = bool(use_jvm_acceleration)
        self._accelerator = accelerator
        self._acceleration = {
            "attempts": 0,
            "successes": 0,
            "fallbacks": 0,
            "bypassed_small_batch": 0,
        }

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
        if self._use_jvm_acceleration:
            return self._snapshot_accelerated()
        return self._snapshot_python()

    def _snapshot_python(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }
        for key, points in self._histograms.items():
            values = [p.value for p in points]
            if values:
                result["histograms"][key] = self._python_histogram_fields(values)
        return result

    def _snapshot_accelerated(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }
        keys: list[str] = []
        series: list[list[float]] = []
        total_values = 0
        for key, points in self._histograms.items():
            values = [point.value for point in points]
            if not values:
                continue
            keys.append(key)
            series.append(values)
            total_values += len(values)

        if not series:
            return result

        try:
            accelerator = self._resolve_accelerator()
            minimum = int(getattr(accelerator, "minimum_batch_values", 1))
            if total_values < minimum:
                self._acceleration["bypassed_small_batch"] += 1
                return self._snapshot_python()

            self._acceleration["attempts"] += 1
            summaries = accelerator.summarize_many(series)
            if len(summaries) != len(keys):
                raise RuntimeError("accelerator returned the wrong summary count")

            for key, summary in zip(keys, summaries):
                fields = summary.metrics_fields()
                result["histograms"][key] = {
                    "count": int(fields["count"]),
                    "min": float(fields["min"]),
                    "max": float(fields["max"]),
                    "mean": float(fields["mean"]),
                    "p50": float(fields["p50"]),
                    "p99": float(fields["p99"]),
                }
            self._acceleration["successes"] += 1
            return result
        except Exception:
            self._acceleration["fallbacks"] += 1
            return self._snapshot_python()

    def acceleration_stats(self) -> Dict[str, int | bool]:
        return {
            "enabled": self._use_jvm_acceleration,
            **self._acceleration,
        }

    def _resolve_accelerator(self) -> Any:
        if self._accelerator is None:
            from skeleton.observability.jvm_accelerator import get_default_accelerator

            self._accelerator = get_default_accelerator()
        return self._accelerator

    @staticmethod
    def _python_histogram_fields(values: list[float]) -> Dict[str, Any]:
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "p50": statistics.median(values),
            "p99": sorted(values)[int(len(values) * 0.99)] if len(values) > 1 else values[0],
        }

    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


class AnomalyDetector:
    """Statistical anomaly detection on event streams.

    Single observations stay on the existing Python path. The optional JVM path
    is only used by observe_many, where one IPC call can cover many rolling
    window calculations.
    """

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        window_size: int = 100,
        *,
        use_jvm_acceleration: bool = False,
        accelerator: Any = None,
    ):
        self._bus = bus
        self._window_size = window_size
        self._values: Deque[float] = deque(maxlen=window_size)
        self._threshold_multiplier = 3.0
        self._use_jvm_acceleration = bool(use_jvm_acceleration)
        self._accelerator = accelerator
        self._acceleration = {
            "attempts": 0,
            "successes": 0,
            "fallbacks": 0,
            "bypassed_small_batch": 0,
        }

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
            self._emit_anomaly(value, mean, stdev)
            return alert

        return None

    def observe_many(self, values: List[float]) -> List[Optional[str]]:
        """Observe a batch, optionally accelerating rolling statistics in Java.

        Results remain ordered one-for-one with input values. The detector's
        Python deque is updated exactly once per input even when Java computes
        the rolling means and standard deviations.
        """
        batch = list(values)
        if not batch:
            return []
        if not self._use_jvm_acceleration or self._window_size < 10:
            return [self.observe(value) for value in batch]

        try:
            accelerator = self._resolve_accelerator()
            minimum = int(getattr(accelerator, "minimum_batch_values", 1))
            if len(batch) < minimum:
                self._acceleration["bypassed_small_batch"] += 1
                return [self.observe(value) for value in batch]

            self._acceleration["attempts"] += 1
            rows = accelerator.scan_anomalies(
                list(self._values),
                batch,
                window_size=self._window_size,
                threshold=self._threshold_multiplier,
            )
            if len(rows) != len(batch):
                raise RuntimeError("accelerator returned the wrong anomaly row count")

            alerts: List[Optional[str]] = []
            for value, row in zip(batch, rows):
                self._values.append(value)
                if row.ready and row.anomalous:
                    alert = (
                        f"Anomaly detected: {value:.2f} "
                        f"(mean={row.mean:.2f}, std={row.stdev:.2f})"
                    )
                    self._emit_anomaly(value, row.mean, row.stdev)
                    alerts.append(alert)
                else:
                    alerts.append(None)
            self._acceleration["successes"] += 1
            return alerts
        except Exception:
            self._acceleration["fallbacks"] += 1
            return [self.observe(value) for value in batch]

    def acceleration_stats(self) -> Dict[str, int | bool]:
        return {
            "enabled": self._use_jvm_acceleration,
            **self._acceleration,
        }

    def _resolve_accelerator(self) -> Any:
        if self._accelerator is None:
            from skeleton.observability.jvm_accelerator import get_default_accelerator

            self._accelerator = get_default_accelerator()
        return self._accelerator

    def _emit_anomaly(self, value: float, mean: float, stdev: float) -> None:
        if self._bus:
            self._bus.emit("observability.anomaly", {
                "value": value,
                "mean": mean,
                "stdev": stdev,
                "threshold": self._threshold_multiplier,
            })

    def stats(self) -> Dict[str, Any]:
        return {
            "observations": len(self._values),
            "window_size": self._window_size,
            "threshold": self._threshold_multiplier,
        }
