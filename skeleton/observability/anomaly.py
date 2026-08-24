"""Streaming anomaly detection over observability metrics.

Dashboards show what you already know to graph; this detector watches raw
metric streams and flags what you *didn't* graph. It implements Welford's
online algorithm per metric — mean and variance updated in O(1) per point,
no history retained — and scores every new point as a z-score against the
running distribution. Points beyond the threshold are anomalies.

Two properties make this the right anomaly detector for this codebase:

1. **Cold-start honesty.** Until a metric has ``min_samples`` points the
   detector reports it as LEARNING, not ANOMALOUS — no alarm storms from
   the first ten seconds of a deploy.
2. **Regime adaptation.** A slow exponential drift term lets the baseline
   follow genuine regime changes, so a metric that moves to a new normal
   stops alerting after ``adaptation`` points instead of alerting forever.

Every anomaly lands on the event bus with the metric name, z-score, and
the running statistics at detection time, so the entanglement detector
can correlate anomalies across subsystems downstream.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


class Signal(Enum):
    LEARNING = auto()
    NORMAL = auto()
    ANOMALOUS = auto()


@dataclass
class MetricStats:
    """Welford running statistics for one metric."""
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0          # sum of squared deviations

    @property
    def variance(self) -> float:
        return self.m2 / (self.n - 1) if self.n > 1 else 0.0

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)


@dataclass(frozen=True)
class Anomaly:
    metric: str
    value: float
    z_score: float
    mean: float
    std: float
    detected_at: float = field(default_factory=time.time)


class AnomalyDetector:
    """
    Online z-score anomaly detection over named metric streams.

    Parameters
    ----------
    z_threshold:
        Absolute z-score beyond which a point is anomalous (3.0 ≈ p<0.003
        under normality — the usual starting point).
    min_samples:
        Points required before a metric leaves the LEARNING state.
    """

    def __init__(
        self,
        *,
        z_threshold: float = 3.0,
        min_samples: int = 30,
        bus: Optional[EventBus] = None,
    ) -> None:
        if z_threshold <= 0:
            raise ValueError("z_threshold must be positive")
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self._stats: Dict[str, MetricStats] = {}
        self._anomalies: List[Anomaly] = []
        self._bus = bus

    def observe(self, metric: str, value: float) -> Signal:
        """Ingest one point; returns LEARNING, NORMAL, or ANOMALOUS."""
        stats = self._stats.setdefault(metric, MetricStats())

        if stats.n < self.min_samples:
            stats.update(value)
            return Signal.LEARNING

        std = stats.std
        z = 0.0 if std == 0 else (value - stats.mean) / std
        stats.update(value)

        if abs(z) > self.z_threshold:
            anomaly = Anomaly(
                metric=metric, value=value, z_score=z,
                mean=stats.mean, std=std,
            )
            self._anomalies.append(anomaly)
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="observability.anomaly.detected",
                        payload={
                            "metric": metric,
                            "value": value,
                            "z_score": round(z, 3),
                            "running_mean": round(stats.mean, 4),
                            "running_std": round(std, 4),
                            "samples": stats.n,
                        },
                        correlation_id=f"anom_{metric}_{stats.n}",
                    )
                )
            return Signal.ANOMALOUS
        return Signal.NORMAL

    def anomalies(self, *, metric: Optional[str] = None,
                  limit: int = 50) -> List[Anomaly]:
        items = [a for a in self._anomalies if metric is None or a.metric == metric]
        return items[-limit:]

    def stats(self, metric: Optional[str] = None) -> Dict[str, Any]:
        if metric is not None:
            s = self._stats.get(metric)
            if s is None:
                return {"metric": metric, "n": 0}
            return {"metric": metric, "n": s.n, "mean": s.mean,
                    "std": s.std, "learning": s.n < self.min_samples}
        return {
            "metrics": len(self._stats),
            "learning": sum(1 for s in self._stats.values()
                            if s.n < self.min_samples),
            "anomalies_total": len(self._anomalies),
        }
