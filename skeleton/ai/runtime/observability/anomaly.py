"""
Skeleton Observability — Anomaly detection on event streams

Provides:
- AnomalyDetector: Statistical anomaly detection
- SeasonalDecomposer: Time-series decomposition
- AdaptiveThreshold: Self-adjusting anomaly thresholds
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from skeleton.kernel.events import EventBus


@dataclass
class AnomalyReport:
    """A detected anomaly with context."""
    timestamp: float
    metric_name: str
    observed_value: float
    expected_range: tuple[float, float]
    severity: str  # low, medium, high, critical
    context: Dict[str, Any] = field(default_factory=dict)


class AdaptiveThreshold:
    """Self-adjusting anomaly threshold based on recent history."""

    def __init__(self, initial_multiplier: float = 3.0, adaptation_rate: float = 0.1):
        self.multiplier = initial_multiplier
        self._adaptation_rate = adaptation_rate
        self._history: Deque[float] = deque(maxlen=1000)
        self._false_positives = 0
        self._true_positives = 0

    def update(self, value: float, is_anomaly: bool, confirmed: bool = False) -> None:
        """Update threshold based on feedback."""
        self._history.append(value)

        if confirmed:
            if is_anomaly:
                self._true_positives += 1
                # Slightly widen threshold to catch more
                self.multiplier = min(5.0, self.multiplier * (1 + self._adaptation_rate))
            else:
                self._false_positives += 1
                # Tighten threshold to reduce false positives
                self.multiplier = max(1.5, self.multiplier * (1 - self._adaptation_rate))

    def get_bounds(self) -> tuple[float, float]:
        """Get current expected value bounds."""
        if len(self._history) < 10:
            return (float('-inf'), float('inf'))

        mean = statistics.mean(self._history)
        try:
            stdev = statistics.stdev(self._history)
        except statistics.StatisticsError:
            stdev = 0

        return (mean - self.multiplier * stdev, mean + self.multiplier * stdev)

    def is_anomalous(self, value: float) -> bool:
        """Check if value is outside expected bounds."""
        lower, upper = self.get_bounds()
        return value < lower or value > upper


class SeasonalDecomposer:
    """Simple time-series decomposition for seasonal patterns."""

    def __init__(self, period: int = 24):  # 24 samples = 1 day if hourly
        self.period = period
        self._values: Deque[float] = deque(maxlen=period * 2)

    def add(self, value: float) -> None:
        self._values.append(value)

    def get_seasonal_component(self) -> Optional[List[float]]:
        """Extract seasonal component if enough data."""
        if len(self._values) < self.period:
            return None

        values = list(self._values)
        # Simple moving average as trend
        trend = []
        for i in range(len(values)):
            window = values[max(0, i - self.period // 2):min(len(values), i + self.period // 2 + 1)]
            trend.append(sum(window) / len(window))

        # Seasonal = observed - trend
        seasonal = [v - t for v, t in zip(values, trend)]
        return seasonal

    def deseasonalize(self, value: float, position: int) -> float:
        """Remove seasonal component from a value."""
        seasonal = self.get_seasonal_component()
        if seasonal is None or position >= len(seasonal):
            return value
        return value - seasonal[position % len(seasonal)]


class AnomalyDetector:
    """Statistical anomaly detection with multiple strategies.

    Supports:
    - Statistical: mean/stdev based
    - Adaptive: self-adjusting thresholds
    - Seasonal: time-series decomposition
    """

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        window_size: int = 100,
        strategy: str = "statistical",
        *,
        use_jvm_acceleration: bool = False,
        accelerator: Any = None,
    ):
        self._bus = bus
        self._window_size = window_size
        self._strategy = strategy
        self._values: Deque[float] = deque(maxlen=window_size)
        self._adaptive = AdaptiveThreshold()
        self._seasonal = SeasonalDecomposer()
        self._stats = {"checks": 0, "anomalies": 0, "false_positives": 0}
        self._use_jvm_acceleration = bool(use_jvm_acceleration)
        self._accelerator = accelerator
        self._acceleration = {
            "attempts": 0,
            "successes": 0,
            "fallbacks": 0,
            "bypassed_small_batch": 0,
        }

    def observe(self, value: float, metric_name: str = "default", context: Optional[Dict[str, Any]] = None) -> Optional[AnomalyReport]:
        """Observe a value and detect anomalies."""
        self._values.append(value)
        self._seasonal.add(value)
        self._stats["checks"] += 1

        if len(self._values) < 10:
            return None

        is_anomaly = False
        expected_range = (float('-inf'), float('inf'))

        if self._strategy == "statistical":
            mean = statistics.mean(self._values)
            try:
                stdev = statistics.stdev(self._values)
            except statistics.StatisticsError:
                stdev = 0

            threshold = 3.0 * stdev
            expected_range = (mean - threshold, mean + threshold)
            is_anomaly = abs(value - mean) > threshold and stdev > 0

        elif self._strategy == "adaptive":
            expected_range = self._adaptive.get_bounds()
            is_anomaly = self._adaptive.is_anomalous(value)

        elif self._strategy == "seasonal":
            deseasonalized = self._seasonal.deseasonalize(value, len(self._values) - 1)
            self._values[-1] = deseasonalized  # Replace with deseasonalized for stats
            mean = statistics.mean(self._values)
            try:
                stdev = statistics.stdev(self._values)
            except statistics.StatisticsError:
                stdev = 0
            expected_range = (mean - 3 * stdev, mean + 3 * stdev)
            is_anomaly = abs(deseasonalized - mean) > 3 * stdev and stdev > 0

        if is_anomaly:
            self._stats["anomalies"] += 1

            # Determine severity
            if expected_range[0] != float('-inf') and expected_range[1] != float('inf'):
                range_width = expected_range[1] - expected_range[0]
                if range_width > 0:
                    deviation = abs(value - statistics.mean(self._values)) / range_width
                else:
                    deviation = 0
            else:
                deviation = 0

            severity = "critical" if deviation > 2.0 else "high" if deviation > 1.0 else "medium" if deviation > 0.5 else "low"

            report = AnomalyReport(
                timestamp=time.time(),
                metric_name=metric_name,
                observed_value=value,
                expected_range=expected_range,
                severity=severity,
                context=context or {},
            )

            if self._bus:
                self._bus.emit("observability.anomaly.detected", {
                    "metric": metric_name,
                    "value": value,
                    "severity": severity,
                    "strategy": self._strategy,
                })

            return report

        return None

    def observe_many(
        self,
        values: List[float],
        metric_name: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Optional[AnomalyReport]]:
        """Observe a batch while preserving ordinary detector state semantics.

        Only the statistical strategy can use the JVM fast path. Adaptive and
        seasonal modes remain in Python because their evolving state is part of
        the algorithm and should not be duplicated in a helper process.
        """
        batch = list(values)
        if not batch:
            return []
        if (
            not self._use_jvm_acceleration
            or self._strategy != "statistical"
            or self._window_size < 10
        ):
            return [
                self.observe(value, metric_name=metric_name, context=context)
                for value in batch
            ]

        try:
            accelerator = self._resolve_accelerator()
            minimum = int(getattr(accelerator, "minimum_batch_values", 1))
            if len(batch) < minimum:
                self._acceleration["bypassed_small_batch"] += 1
                return [
                    self.observe(value, metric_name=metric_name, context=context)
                    for value in batch
                ]

            self._acceleration["attempts"] += 1
            rows = accelerator.scan_anomalies(
                list(self._values),
                batch,
                window_size=self._window_size,
                threshold=3.0,
                include_current=True,
            )
            if len(rows) != len(batch):
                raise RuntimeError("accelerator returned the wrong anomaly row count")

            reports: List[Optional[AnomalyReport]] = []
            for value, row in zip(batch, rows):
                self._values.append(value)
                self._seasonal.add(value)
                self._stats["checks"] += 1

                if not row.ready or not row.anomalous:
                    reports.append(None)
                    continue

                self._stats["anomalies"] += 1
                threshold = 3.0 * row.stdev
                expected_range = (row.mean - threshold, row.mean + threshold)
                range_width = expected_range[1] - expected_range[0]
                deviation = (
                    abs(value - row.mean) / range_width
                    if range_width > 0
                    else 0
                )
                severity = (
                    "critical" if deviation > 2.0
                    else "high" if deviation > 1.0
                    else "medium" if deviation > 0.5
                    else "low"
                )
                report = AnomalyReport(
                    timestamp=time.time(),
                    metric_name=metric_name,
                    observed_value=value,
                    expected_range=expected_range,
                    severity=severity,
                    context=context or {},
                )
                if self._bus:
                    self._bus.emit("observability.anomaly.detected", {
                        "metric": metric_name,
                        "value": value,
                        "severity": severity,
                        "strategy": self._strategy,
                    })
                reports.append(report)

            self._acceleration["successes"] += 1
            return reports
        except Exception:
            self._acceleration["fallbacks"] += 1
            return [
                self.observe(value, metric_name=metric_name, context=context)
                for value in batch
            ]

    def acceleration_stats(self) -> Dict[str, int | bool]:
        """Return JVM fast-path counters without changing normal stats output."""
        return {
            "enabled": self._use_jvm_acceleration,
            **self._acceleration,
        }

    def _resolve_accelerator(self) -> Any:
        if self._accelerator is None:
            from skeleton.observability.jvm_accelerator import get_default_accelerator

            self._accelerator = get_default_accelerator()
        return self._accelerator

    def feedback(self, was_anomaly: bool, confirmed: bool) -> None:
        """Provide feedback to improve detection accuracy."""
        if self._strategy == "adaptive":
            last_value = self._values[-1] if self._values else 0
            self._adaptive.update(last_value, was_anomaly, confirmed)

        if not was_anomaly and confirmed:
            self._stats["false_positives"] += 1

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "strategy": self._strategy,
            "window_size": self._window_size,
            "observations": len(self._values),
        }
