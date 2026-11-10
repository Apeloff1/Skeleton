"""Soak runner: drive a workload repeatedly, by iterations and/or wall time."""
from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .stats import Summary, summarize

Clock = Callable[[], float]


@dataclass(frozen=True)
class SoakConfig:
    iterations: int = 20
    duration_s: Optional[float] = None  # stop early once exceeded
    warmup: int = 1  # discarded iterations
    max_consecutive_errors: int = 3

    def __post_init__(self) -> None:
        if type(self.iterations) is not int or not 1 <= self.iterations <= 100000:
            raise ValueError("iterations must be bounded")
        if type(self.warmup) is not int or not 0 <= self.warmup <= 10000:
            raise ValueError("warmup must be bounded")
        if self.duration_s is not None and (type(self.duration_s) not in (int, float)
                or not math.isfinite(self.duration_s) or not 0 < self.duration_s <= 86400):
            raise ValueError("duration must be finite and bounded")
        if type(self.max_consecutive_errors) is not int or not 1 <= self.max_consecutive_errors <= 100000:
            raise ValueError("consecutive error limit must be bounded")


@dataclass
class SoakResult:
    name: str
    samples_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    aborted: bool = False
    stopped_by_duration: bool = False
    warmup_errors: int = 0

    @property
    def summary(self) -> Summary:
        return summarize(self.samples_ms, len(self.errors))


def run_soak(name: str, workload: Callable[[], object], config: SoakConfig = SoakConfig(),
             clock: Clock = time.perf_counter) -> SoakResult:
    """Run ``workload`` ``warmup + iterations`` times; exceptions count as errors."""
    if not callable(workload):
        raise ValueError("measured workload callable required")
    res = SoakResult(name)
    for _ in range(config.warmup):
        try:
            workload()
        except Exception:
            res.warmup_errors += 1
    started = clock()
    streak = 0
    for _ in range(config.iterations):
        if config.duration_s is not None and clock() - started >= config.duration_s:
            res.stopped_by_duration = True
            break
        t0 = clock()
        try:
            workload()
        except Exception as exc:
            res.errors.append(type(exc).__name__)
            streak += 1
            if streak >= config.max_consecutive_errors:
                res.aborted = True
                break
            continue
        streak = 0
        elapsed = (clock() - t0) * 1000.0
        if not math.isfinite(elapsed) or elapsed <= 0:
            res.errors.append("InvalidClock")
            res.aborted = True
            break
        res.samples_ms.append(elapsed)
    return res
