"""Sampling for observability — probabilistic decisions.

Production systems can't trace/meter every hop; the sampler flips a
coin per decision and keeps statistics if callers want verification.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from skeleton.kernel.errors import KernelError


class SamplingError(KernelError):
    code = "OBS.SAMPLING"


@dataclass
class SamplerStats:
    total: int = 0
    kept: int = 0
    dropped: int = 0

    @property
    def ratio(self) -> float:
        return self.kept / self.total if self.total else 0.0


class Sampler:
    """Head-based probabilistic sampler."""

    def __init__(self, *, ratio: float = 1.0, rng: Optional[random.Random] = None) -> None:
        if not 0.0 <= ratio <= 1.0:
            raise SamplingError("ratio must be 0..1")
        self.ratio = ratio
        self._rng = rng or random.Random()
        self.stats = SamplerStats()

    def keep(self) -> bool:
        self.stats.total += 1
        take = self._rng.random() < self.ratio
        if take:
            self.stats.kept += 1
        else:
            self.stats.dropped += 1
        return take


def default_sampler() -> Sampler:
    """Full-tracing by default; callers wire 0.1 sample rate in production."""
    return Sampler(ratio=1.0)
