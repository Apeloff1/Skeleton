"""Sliding-window counters — kernel telemetry primitives.

Rates, latencies, error counts: the kernel needs cheap, bounded-memory
answers to "how much of X in the last N seconds". Ring buffers over
fixed buckets give O(1) writes and O(buckets) reads with zero
dependencies — good enough for backpressure signals, health checks,
and the observability package to build on.

- :class:`SlidingCounter` — event counts over a time window.
- :class:`SlidingGauge` — min/max/last over the same window.
- :class:`WindowedLatency` — approximate percentiles via bucketed
  reservoir (p50/p95/p99 without storing samples).
"""

from __future__ import annotations

import time
from bisect import bisect_right
from typing import Callable, List, Optional, Tuple

from .errors import KernelError


class TelemetryError(KernelError):
    code = "KRN.TELEMETRY"


class _Window:
    """Ring of per-bucket values aligned to bucket boundaries."""

    def __init__(self, buckets: int, bucket_s: float, clock: Optional[Callable[[], float]]) -> None:
        if buckets < 2 or bucket_s <= 0:
            raise TelemetryError(
                "need >= 2 buckets and a positive bucket width",
                context={"buckets": buckets, "bucket_s": bucket_s},
            )
        self.buckets = buckets
        self.bucket_s = float(bucket_s)
        self._now = clock or time.monotonic
        self._values: List[float] = [0.0] * buckets
        self._heads: List[int] = [-1] * buckets  # bucket epoch each slot holds

    def _index(self, t: float) -> Tuple[int, int]:
        epoch = int(t // self.bucket_s)
        return epoch, epoch % self.buckets

    def _slot(self, t: float, *, create: bool) -> Tuple[Optional[int], int]:
        epoch, idx = self._index(t)
        if self._heads[idx] != epoch:
            if not create and self._heads[idx] < epoch - self.buckets:
                return None, epoch  # stale beyond window
            if create or self._heads[idx] < epoch:
                self._values[idx] = 0.0
                self._heads[idx] = epoch
        return idx, epoch

    def add(self, value: float, at: Optional[float] = None) -> None:
        idx, _ = self._slot(self._now() if at is None else at, create=True)
        assert idx is not None
        self._values[idx] += value

    def live(self) -> List[float]:
        """Values for buckets still inside the window, oldest first."""
        now_epoch = int(self._now() // self.bucket_s)
        out = []
        for epoch in range(now_epoch - self.buckets + 1, now_epoch + 1):
            idx = epoch % self.buckets
            out.append(self._values[idx] if self._heads[idx] == epoch else 0.0)
        return out

    @property
    def window_s(self) -> float:
        return self.buckets * self.bucket_s


class SlidingCounter:
    """Counts events over a sliding window."""

    def __init__(self, window_s: float = 60.0, buckets: int = 60,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._w = _Window(buckets, window_s / buckets, clock)

    def hit(self, n: float = 1.0) -> None:
        self._w.add(n)

    @property
    def total(self) -> float:
        return sum(self._w.live())

    @property
    def rate_per_sec(self) -> float:
        return self.total / self._w.window_s


class SlidingGauge:
    """min/max/last of samples over a sliding window (approximate: min/max
    are bucket-level aggregates, not sample-level)."""

    def __init__(self, window_s: float = 60.0, buckets: int = 60,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._count = _Window(buckets, window_s / buckets, clock)
        self._sum = _Window(buckets, window_s / buckets, clock)
        self._min = _Window(buckets, window_s / buckets, clock)
        self._max = _Window(buckets, window_s / buckets, clock)
        self._last = _Window(buckets, window_s / buckets, clock)

    def observe(self, value: float) -> None:
        # _Window is additive; min/max/last need slot access — extend _Window
        # semantics via add() on transformed values is wrong, so drive slots:
        w = self._count
        idx, _ = w._slot(w._now(), create=True)
        assert idx is not None
        fresh = w._values[idx] == 0.0 and w._sum._values[idx] == 0.0
        w._values[idx] += 1
        self._sum._values[idx] += value
        self._sum._heads[idx] = w._heads[idx]
        for win, val, keep in (
            (self._min, value, min),
            (self._max, value, max),
        ):
            win._heads[idx] = w._heads[idx]
            win._values[idx] = value if fresh else keep(win._values[idx], value)
        self._last._heads[idx] = w._heads[idx]
        self._last._values[idx] = value

    def snapshot(self) -> dict:
        counts = self._count.live()
        mins = [v for c, v in zip(counts, self._min.live()) if c > 0]
        maxs = [v for c, v in zip(counts, self._max.live()) if c > 0]
        total = sum(counts)
        return {
            "count": int(total),
            "mean": (sum(self._sum.live()) / total) if total else None,
            "min": min(mins) if mins else None,
            "max": max(maxs) if maxs else None,
            "last": next((v for v in reversed(self._last.live())), None) if total else None,
        }


class WindowedLatency:
    """Approximate percentiles over a sliding window using a bounded
    reservoir of (value, bucket_epoch) samples — evicted wholesale when
    their bucket leaves the window."""

    def __init__(self, window_s: float = 60.0, buckets: int = 60,
                 reservoir_per_bucket: int = 64,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if reservoir_per_bucket < 8:
            raise TelemetryError("reservoir_per_bucket must be >= 8")
        self._w = _Window(buckets, window_s / buckets, clock)
        self._cap = reservoir_per_bucket
        self._samples: List[Tuple[int, float]] = []  # (bucket_epoch, ms)

    def observe(self, latency_ms: float) -> None:
        epoch = int(self._w._now() // self._w.bucket_s)
        bucket_samples = [s for s in self._samples if s[0] == epoch]
        if len(bucket_samples) >= self._cap:
            # random-free eviction: drop the oldest in this bucket
            oldest_idx = next(i for i, s in enumerate(self._samples) if s[0] == epoch)
            self._samples.pop(oldest_idx)
        self._samples.append((epoch, latency_ms))
        self._evict(epoch)

    def _evict(self, now_epoch: int) -> None:
        cutoff = now_epoch - self._w.buckets + 1
        self._samples = [s for s in self._samples if s[0] >= cutoff]

    def percentile(self, p: float) -> Optional[float]:
        if not 0 < p <= 100:
            raise TelemetryError("percentile must be in (0, 100]", context={"p": p})
        self._evict(int(self._w._now() // self._w.bucket_s))
        if not self._samples:
            return None
        values = sorted(v for _, v in self._samples)
        rank = max(1, round(p / 100 * len(values)))
        return values[min(rank, len(values)) - 1]

    def summary(self) -> dict:
        return {
            "n": len(self._samples),
            "p50": self.percentile(50),
            "p95": self.percentile(95),
            "p99": self.percentile(99),
            "window_s": self._w.window_s,
        }
