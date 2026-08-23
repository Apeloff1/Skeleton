"""Metrics — counters, gauges, histograms with sliding-window percentiles.

A fully in-process metrics registry. Instruments carry labels; the registry
renders both a JSON snapshot and a Prometheus-compatible text exposition.
Histograms retain a bounded sliding window of raw observations so percentiles
are computed over recent data, not cumulative history.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

LabelSet = Tuple[Tuple[str, str], ...]


def _labels(labels: Optional[Dict[str, str]]) -> LabelSet:
    return tuple(sorted((labels or {}).items()))


def _render_labels(ls: LabelSet) -> str:
    if not ls:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in ls)
    return "{" + inner + "}"


class Counter:
    def __init__(self, name: str, help_text: str) -> None:
        self.name, self.help_text = name, help_text
        self._values: Dict[LabelSet, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        if amount < 0:
            raise ValueError("counters only increase")
        with self._lock:
            self._values[_labels(labels)] += amount

    def collect(self) -> Dict[LabelSet, float]:
        return dict(self._values)


class Gauge:
    def __init__(self, name: str, help_text: str) -> None:
        self.name, self.help_text = name, help_text
        self._values: Dict[LabelSet, float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            self._values[_labels(labels)] = value

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            ls = _labels(labels)
            self._values[ls] = self._values.get(ls, 0.0) + amount

    def dec(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        self.inc(-amount, labels)

    def collect(self) -> Dict[LabelSet, float]:
        return dict(self._values)


@dataclass
class _Window:
    observations: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=2048))


class Histogram:
    """Sliding-window histogram with exact percentile computation."""

    def __init__(self, name: str, help_text: str, window_seconds: float = 600.0) -> None:
        self.name, self.help_text = name, help_text
        self._window_seconds = window_seconds
        self._windows: Dict[LabelSet, _Window] = defaultdict(_Window)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            self._windows[_labels(labels)].observations.append((time.time(), value))

    def _prune(self, w: _Window) -> List[float]:
        cutoff = time.time() - self._window_seconds
        while w.observations and w.observations[0][0] < cutoff:
            w.observations.popleft()
        return sorted(v for _, v in w.observations)

    @staticmethod
    def _percentile(sorted_vals: List[float], q: float) -> float:
        if not sorted_vals:
            return 0.0
        idx = min(len(sorted_vals) - 1, max(0, int(q * (len(sorted_vals) - 1))))
        return sorted_vals[idx]

    def summarise(self, labels: Optional[Dict[str, str]] = None,
                  quantiles: Tuple[float, ...] = (0.5, 0.9, 0.99)) -> Dict[str, float]:
        with self._lock:
            vals = self._prune(self._windows[_labels(labels)])
        out: Dict[str, float] = {"count": float(len(vals)),
                                 "sum": float(sum(vals)),
                                 "min": vals[0] if vals else 0.0,
                                 "max": vals[-1] if vals else 0.0}
        for q in quantiles:
            out[f"p{int(q * 100)}"] = self._percentile(vals, q)
        return out


class MetricsRegistry:
    """Central registry: factory + exposition."""

    def __init__(self) -> None:
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}

    def counter(self, name: str, help_text: str = "") -> Counter:
        return self._counters.setdefault(name, Counter(name, help_text))

    def gauge(self, name: str, help_text: str = "") -> Gauge:
        return self._gauges.setdefault(name, Gauge(name, help_text))

    def histogram(self, name: str, help_text: str = "",
                  window_seconds: float = 600.0) -> Histogram:
        return self._histograms.setdefault(name, Histogram(name, help_text, window_seconds))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters": {n: {str(k): v for k, v in c.collect().items()}
                         for n, c in self._counters.items()},
            "gauges": {n: {str(k): v for k, v in g.collect().items()}
                       for n, g in self._gauges.items()},
            "histograms": {n: {"series": len(h._windows)} for n, h in self._histograms.items()},
        }

    def prometheus(self) -> str:
        lines: List[str] = []
        for c in self._counters.values():
            lines.append(f"# HELP {c.name} {c.help_text}\n# TYPE {c.name} counter")
            for ls, v in c.collect().items():
                lines.append(f"{c.name}{_render_labels(ls)} {v}")
        for g in self._gauges.values():
            lines.append(f"# HELP {g.name} {g.help_text}\n# TYPE {g.name} gauge")
            for ls, v in g.collect().items():
                lines.append(f"{g.name}{_render_labels(ls)} {v}")
        for h in self._histograms.values():
            lines.append(f"# HELP {h.name} {h.help_text}\n# TYPE {h.name} summary")
            for ls in h._windows:
                s = h.summarise(dict(ls))
                for q in (0.5, 0.9, 0.99):
                    qv = s[f"p{int(q * 100)}"]
                    qlabels = _render_labels(ls + (("quantile", str(q)),))
                    lines.append(f"{h.name}{qlabels} {qv}")
                lines.append(f"{h.name}_count{_render_labels(ls)} {s['count']}")
                lines.append(f"{h.name}_sum{_render_labels(ls)} {s['sum']}")
        return "\n".join(lines) + "\n"
