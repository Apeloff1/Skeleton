"""Linux cgroup-v2 CPU throttling telemetry for offline AI job concurrency.

Kernel cpu.stat counters are cumulative. Admission uses period deltas, never
converts a host CPU count into an invented quota or a fabricated GPU budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import threading


@dataclass(frozen=True, slots=True)
class CPUThrottleSample:
    periods: int
    throttled_periods: int
    throttled_usec: int

    def __post_init__(self) -> None:
        for key in ("periods", "throttled_periods", "throttled_usec"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError("invalid cgroup CPU counter")
        if self.throttled_periods > self.periods:
            raise ValueError("throttled periods exceed total periods")


def probe_cpu_throttle(root: str | Path = "/sys/fs/cgroup") -> CPUThrottleSample | None:
    """Read v2 cpu.stat; unknown is not zero throttling."""
    if sys.platform != "linux":
        return None
    try:
        raw = (Path(root) / "cpu.stat").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None
    if len(raw) > 4096:
        return None
    counters: dict[str, int] = {}
    for line in raw.splitlines():
        fields = line.split()
        if (len(fields) != 2 or fields[0] in counters
                or not fields[1].isascii() or not fields[1].isdecimal()):
            return None
        counters[fields[0]] = int(fields[1])
    if not {"nr_periods", "nr_throttled", "throttled_usec"} <= counters.keys():
        return None
    try:
        return CPUThrottleSample(
            counters["nr_periods"], counters["nr_throttled"],
            counters["throttled_usec"],
        )
    except ValueError:
        return None


class CPUThrottleController:
    """Hysteresis over observed CFS throttled-period ratios.

    No sample or counter reset clears a prior pressure hold. Only a subsequent
    valid delta with enough periods can authorize recovery. No per-file quota.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._previous: CPUThrottleSample | None = None
        self._last: CPUThrottleSample | None = None
        self._ratio: float | None = None
        self._throttled = False
        self._observations = 0
        self._transitions = 0

    def observe(self, sample: CPUThrottleSample | None) -> None:
        if sample is not None and not isinstance(sample, CPUThrottleSample):
            raise TypeError("typed CPU throttling telemetry required")
        with self._lock:
            self._observations += 1
            self._last = sample
            if sample is None:
                return
            previous = self._previous
            self._previous = sample
            if previous is None:
                return
            if (sample.periods < previous.periods
                    or sample.throttled_periods < previous.throttled_periods
                    or sample.throttled_usec < previous.throttled_usec):
                return
            periods = sample.periods - previous.periods
            throttled = sample.throttled_periods - previous.throttled_periods
            if periods <= 0 or throttled > periods:
                return
            self._ratio = throttled / periods
            prior = self._throttled
            if self._ratio >= 0.20:
                self._throttled = True
            elif self._ratio <= 0.05:
                self._throttled = False
            if prior != self._throttled:
                self._transitions += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            sample = self._last
            return {
                "schema": "skeleton.offline.cpu-throttle.v1",
                "measured": sample is not None,
                "periods": sample.periods if sample else None,
                "throttled_periods": sample.throttled_periods if sample else None,
                "throttled_usec": sample.throttled_usec if sample else None,
                "observed_throttled_ratio": self._ratio,
                "backpressure": self._throttled,
                "observations": self._observations,
                "transitions": self._transitions,
            }


__all__ = ["CPUThrottleSample", "CPUThrottleController", "probe_cpu_throttle"]
