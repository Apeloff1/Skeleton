"""Latency statistics (nearest-rank-interpolated percentiles)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Dict, Sequence


def percentile(samples: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile, ``pct`` in [0, 100]."""
    if not samples:
        raise ValueError("percentile of empty sample set")
    if not 0.0 <= pct <= 100.0 or math.isnan(pct):
        raise ValueError(f"pct out of range: {pct!r}")
    if type(samples) not in (list, tuple) or len(samples) > 100000:
        raise ValueError("invalid bounded latency inventory")
    if any(type(s) not in (float, int) or not math.isfinite(s) or s < 0 for s in samples):
        raise ValueError("nonfinite or negative latency sample")
    data = sorted(float(s) for s in samples)
    if len(data) == 1:
        return data[0]
    rank = (pct / 100.0) * (len(data) - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (rank - lo)


@dataclass(frozen=True)
class Summary:
    count: int
    errors: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    error_rate: float
    drift_ratio: float  # mean(last third) / mean(first third); >1 means slowing down

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)

    def metric(self, name: str) -> float:
        if name not in self.__dataclass_fields__:
            raise KeyError(f"unknown metric: {name}")
        return float(getattr(self, name))


def _drift(samples: Sequence[float]) -> float:
    n = len(samples)
    if n < 3:
        return 1.0
    third = n // 3
    head = sum(samples[:third]) / third
    tail = sum(samples[-third:]) / third
    if head <= 0:
        return 1.0
    return tail / head


def summarize(samples_ms: Sequence[float], errors: int = 0) -> Summary:
    if type(errors) is not int or not 0 <= errors <= 100000:
        raise ValueError("unbounded error count")
    if type(samples_ms) not in (list, tuple) or len(samples_ms) > 100000:
        raise ValueError("unbounded latency samples")
    if any(type(s) not in (float, int) or not math.isfinite(s) or s < 0 for s in samples_ms):
        raise ValueError("nonfinite or negative latency sample")
    total = len(samples_ms) + errors
    if not samples_ms:
        return Summary(total, errors, 0.0, 0.0, 0.0, 0.0, 0.0,
                       1.0 if total else 0.0, 1.0)
    return Summary(
        count=total,
        errors=errors,
        mean_ms=sum(samples_ms) / len(samples_ms),
        p50_ms=percentile(samples_ms, 50),
        p95_ms=percentile(samples_ms, 95),
        p99_ms=percentile(samples_ms, 99),
        max_ms=max(samples_ms),
        error_rate=errors / total,
        drift_ratio=_drift(list(samples_ms)),
    )
