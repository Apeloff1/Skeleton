"""Metrics registry — typed metrics with labels, windows, and rollups.

Central typed metric store (counters, gauges, histograms, timers)
with label dimensions, sliding-window statistics, cross-metric
rollups, and threshold-based alerting hooks. Feeds both the exporter
(Prometheus format) and the dashboard cards.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


def _label_key(labels: Optional[Dict[str, str]]) -> Tuple:
    return tuple(sorted((labels or {}).items()))


@dataclass
class HistogramSeries:
    values: List[Tuple[int, float]] = field(default_factory=list)

    def record(self, value: float) -> None:
        self.values.append((time.time_ns(), value))
        if len(self.values) > 1000:
            self.values.pop(0)

    def percentile(self, p: float) -> float:
        if not self.values:
            return 0.0
        vals = sorted(v for _, v in self.values)
        idx = min(len(vals) - 1, int(len(vals) * p))
        return vals[idx]

    def window_stats(self, window_s: float) -> Dict[str, float]:
        cutoff = time.time_ns() - int(window_s * 1e9)
        vals = [v for t, v in self.values if t >= cutoff]
        if not vals:
            return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        vals.sort()
        n = len(vals)
        return {
            "count": n,
            "mean": round(sum(vals) / n, 4),
            "p50": round(vals[n // 2], 4),
            "p95": round(vals[min(n - 1, int(n * 0.95))], 4),
            "p99": round(vals[min(n - 1, int(n * 0.99))], 4),
        }


class MetricsRegistry:
    """Typed metrics with labels and sliding windows."""

    def __init__(self):
        self._counters: Dict[Tuple, float] = {}
        self._gauges: Dict[Tuple, float] = {}
        self._histograms: Dict[Tuple, HistogramSeries] = {}
        self._alert_hooks: List[Callable[[str, float, float], None]] = []
        self._thresholds: Dict[str, float] = {}

    def _key(self, kind: str, name: str, labels: Optional[Dict[str, str]]) -> Tuple:
        return (kind, name, _label_key(labels))

    def counter(self, name: str, value: float = 1.0,
                labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key("counter", name, labels)
        self._counters[key] = self._counters.get(key, 0.0) + value
        self._check_threshold(name, self._counters[key])

    def gauge(self, name: str, value: float,
              labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key("gauge", name, labels)
        self._gauges[key] = value
        self._check_threshold(name, value)

    def observe(self, name: str, value: float,
                labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key("histogram", name, labels)
        self._histograms.setdefault(key, HistogramSeries()).record(value)

    def timer(self, name: str, labels: Optional[Dict[str, str]] = None):
        registry = self

        class _Timer:
            def __enter__(self):
                self.start = time.time_ns()
                return self

            def __exit__(self, *exc):
                registry.observe(name, (time.time_ns() - self.start) / 1e6, labels)
                return False

        return _Timer()

    def set_threshold(self, name: str, threshold: float) -> None:
        self._thresholds[name] = threshold

    def on_threshold(self, hook: Callable[[str, float, float], None]) -> None:
        self._alert_hooks.append(hook)

    def _check_threshold(self, name: str, value: float) -> None:
        threshold = self._thresholds.get(name)
        if threshold is not None and value > threshold:
            for hook in self._alert_hooks:
                try:
                    hook(name, value, threshold)
                except Exception:  # noqa: BLE001
                    pass

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        return self._counters.get(self._key("counter", name, labels), 0.0)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        return self._gauges.get(self._key("gauge", name, labels))

    def histogram_stats(self, name: str, window_s: float = 300.0,
                        labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        series = self._histograms.get(self._key("histogram", name, labels))
        return series.window_stats(window_s) if series else {"count": 0}

    def rollup(self) -> Dict[str, Any]:
        counters: Dict[str, float] = {}
        for (_, name, _), v in self._counters.items():
            counters[name] = counters.get(name, 0.0) + v
        gauges: Dict[str, float] = {}
        for (_, name, _), v in self._gauges.items():
            gauges[name] = v
        return {"counters": counters, "gauges": gauges, "histograms": len(self._histograms)}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "metrics-registry-card",
            "series": len(self._counters) + len(self._gauges) + len(self._histograms),
            "thresholds": len(self._thresholds),
            "rollup": self.rollup(),
        }
