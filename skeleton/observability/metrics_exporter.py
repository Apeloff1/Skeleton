"""Metrics exporter — Prometheus-compatible metrics endpoint.

Provides a simple metrics exporter that formats subsystem telemetry
into Prometheus text format. Supports counters, gauges, histograms,
and summaries with configurable buckets.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricValue:
    value: float
    timestamp_ns: int
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsExporter:
    """Prometheus-compatible metrics exporter."""

    def __init__(self, subsystem: str):
        self.subsystem = subsystem
        self._counters: Dict[str, List[MetricValue]] = {}
        self._gauges: Dict[str, List[MetricValue]] = {}
        self._histograms: Dict[str, List[MetricValue]] = {}
        self._buckets: Dict[str, List[float]] = {}

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        self._counters.setdefault(name, []).append(MetricValue(value, time.time_ns(), labels or {}))

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        self._gauges.setdefault(name, []).append(MetricValue(value, time.time_ns(), labels or {}))

    def histogram(self, name: str, value: float, buckets: Optional[List[float]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        self._histograms.setdefault(name, []).append(MetricValue(value, time.time_ns(), labels or {}))
        if buckets and name not in self._buckets:
            self._buckets[name] = buckets

    def _format_labels(self, labels: Dict[str, str]) -> str:
        if not labels:
            return ""
        pairs = [f'{k}="{v}"' for k, v in labels.items()]
        return "{" + ",".join(pairs) + "}"

    def render(self) -> str:
        lines: List[str] = []
        for name, values in self._counters.items():
            total = sum(v.value for v in values)
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {total}")
        for name, values in self._gauges.items():
            if values:
                latest = values[-1]
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{self._format_labels(latest.labels)} {latest.value}")
        for name, values in self._histograms.items():
            if values:
                buckets = self._buckets.get(name, [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
                lines.append(f"# TYPE {name} histogram")
                counts = {b: 0 for b in buckets}
                counts[float("inf")] = 0
                for v in values:
                    counts[float("inf")] += 1
                    for b in buckets:
                        if v.value <= b:
                            counts[b] += 1
                for b in buckets:
                    lines.append(f'{name}_bucket{{le="{b}"}} {counts[b]}')
                lines.append(f'{name}_bucket{{le="+Inf"}} {counts[float("inf")]}')
                lines.append(f"{name}_count {counts[float('inf')]}")
                total_sum = sum(v.value for v in values)
                lines.append(f"{name}_sum {total_sum}")
        return "\n".join(lines)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "metrics-exporter-card",
            "subsystem": self.subsystem,
            "counters": len(self._counters),
            "gauges": len(self._gauges),
            "histograms": len(self._histograms),
        }
