"""Runtime controller for the Jeeves absorb plane.

This module owns scheduling policy, not serving.  The controller can run in a
separate task/process and dynamically reduces expensive absorption when the
serving plane reports pressure.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Callable

from .absorb import AbsorbEngine, AbsorbError, KnowledgeSnapshot


@dataclass(frozen=True, slots=True)
class BackpressurePolicy:
    min_batch: int = 1
    normal_batch: int = 64
    burst_batch: int = 256
    high_backlog: int = 1_024
    serving_pressure_cutoff: float = 0.75
    idle_sleep_seconds: float = 0.05

    def __post_init__(self) -> None:
        for name in ("min_batch", "normal_batch", "burst_batch", "high_backlog"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AbsorbError(f"{name} must be a positive integer")
        if self.min_batch > self.normal_batch or self.normal_batch > self.burst_batch:
            raise AbsorbError("batch sizes must satisfy min <= normal <= burst")
        if not 0.0 <= self.serving_pressure_cutoff <= 1.0:
            raise AbsorbError("serving_pressure_cutoff must be between 0 and 1")
        if not math.isfinite(self.idle_sleep_seconds) or self.idle_sleep_seconds < 0:
            raise AbsorbError("idle_sleep_seconds must be finite and non-negative")


PressureProbe = Callable[[], float]


class AbsorbRuntime:
    """SLO-aware runner that keeps absorption perpendicular to inference."""

    def __init__(
        self,
        engine: AbsorbEngine,
        *,
        pressure_probe: PressureProbe | None = None,
        policy: BackpressurePolicy | None = None,
    ) -> None:
        self.engine = engine
        self._pressure_probe = pressure_probe or (lambda: 0.0)
        self.policy = policy or BackpressurePolicy()
        self._stop = asyncio.Event()

    def serving_pressure(self) -> float:
        pressure = float(self._pressure_probe())
        if not math.isfinite(pressure):
            return 1.0
        return max(0.0, min(1.0, pressure))

    def batch_budget(self) -> int:
        pressure = self.serving_pressure()
        if pressure >= self.policy.serving_pressure_cutoff:
            return self.policy.min_batch
        if self.engine.backlog >= self.policy.high_backlog and pressure < 0.35:
            return self.policy.burst_batch
        return self.policy.normal_batch

    def run_once(self) -> KnowledgeSnapshot | None:
        """Process one isolated batch; useful for workers and deterministic tests."""
        if self.engine.backlog == 0:
            return None
        return self.engine.process(max_items=min(self.batch_budget(), self.engine.backlog))

    async def run(self) -> None:
        """Continuously process absorption off the request path.

        CPU/domain processing is moved to a worker thread so an asyncio serving
        loop does not inherit absorb latency.
        """
        self._stop.clear()
        while not self._stop.is_set():
            if self.engine.backlog:
                await asyncio.to_thread(self.run_once)
            else:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.policy.idle_sleep_seconds)
                except TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop.set()
