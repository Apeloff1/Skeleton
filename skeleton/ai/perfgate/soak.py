"""Soak runner: drive a workload repeatedly, by iterations and/or wall time."""
from __future__ import annotations

import time
import traceback
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
        if self.iterations < 1:
            raise ValueError("iterations must be >= 1")
        if self.warmup < 0:
            raise ValueError("warmup must be >= 0")
        if self.duration_s is not None and self.duration_s <= 0:
            raise ValueError("duration_s must be > 0")
        if self.max_consecutive_errors < 1:
            raise ValueError("max_consecutive_errors must be >= 1")


@dataclass
class SoakResult:
    name: str
    samples_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    aborted: bool = False
    stopped_by_duration: bool = False

    @property
    def summary(self) -> Summary:
        return summarize(self.samples_ms, len(self.errors))


def run_soak(name: str, workload: Callable[[], object], config: SoakConfig = SoakConfig(),
             clock: Clock = time.perf_counter) -> SoakResult:
    """Run ``workload`` ``warmup + iterations`` times; exceptions count as errors."""
    for _ in range(config.warmup):
        try:
            workload()
        except Exception:  # warmup failures surface in the measured loop
            pass
    res = SoakResult(name)
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
            res.errors.append(f"{type(exc).__name__}: {exc}")
            streak += 1
            if streak >= config.max_consecutive_errors:
                res.aborted = True
                break
            continue
        streak = 0
        res.samples_ms.append((clock() - t0) * 1000.0)
    return res
