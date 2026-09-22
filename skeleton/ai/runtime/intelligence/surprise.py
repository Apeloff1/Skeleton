"""Surprise-driven novelty detection for the intelligence layer.

Attention is expensive; the system should only spend it where the world
is not behaving the way the world usually behaves. This module scores
each observation by *surprise* — how far it sits from an online model
of what has been seen before — and lets the rest of the stack gate
processing on that score.

Design:

- :class:`OnlineGaussian` — Welford's algorithm; mean/variance updated
  in O(1) per sample, no history retained.
- :class:`SurpriseScorer` — multivariate z-surprise with per-channel
  habituation: a channel that keeps surprising stops being surprising
  (its baseline absorbs the new regime) unless the jump is extreme.
- :class:`NoveltyGate` — threshold + cooldown so downstream consumers
  see a clean admit/suppress decision instead of raw scores.

Numerically stable, stateless across restarts unless snapshotted,
zero dependencies.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Tuple

from ..kernel.errors import SkeletonError


class SurpriseError(SkeletonError):
    code = "INT.SURPRISE"


class OnlineGaussian:
    """Welford online mean/variance for one scalar channel."""

    __slots__ = ("n", "mean", "m2")

    def __init__(self) -> None:
        self.n: int = 0
        self.mean: float = 0.0
        self.m2: float = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    @property
    def variance(self) -> float:
        return self.m2 / (self.n - 1) if self.n > 1 else 0.0

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def z_score(self, x: float) -> float:
        if self.n < 2:
            return 0.0
        sd = self.std
        if sd < 1e-12:
            return 0.0 if abs(x - self.mean) < 1e-12 else float("inf")
        return (x - self.mean) / sd

    def snapshot(self) -> Dict[str, float]:
        return {"n": self.n, "mean": self.mean, "m2": self.m2}


@dataclass
class SurpriseReading:
    channel: str
    value: float
    z: float
    surprise: float           # post-habituation score in [0, 1]
    habituation: float        # current habituation level in [0, 1)
    timestamp: float


class SurpriseScorer:
    """Multichannel surprise with habituation.

    habituation_rate controls how quickly a channel's baseline absorbs a
    persistently surprising regime: raw |z| is discounted by the channel's
    habituation level, and habituation itself rises toward the recent
    surprise level at ``habituation_rate`` per reading.
    """

    def __init__(self, *, habituation_rate: float = 0.05, max_z: float = 8.0) -> None:
        if not 0.0 < habituation_rate < 1.0:
            raise SurpriseError(
                "habituation_rate must be in (0, 1)",
                context={"habituation_rate": habituation_rate},
            )
        self.habituation_rate = habituation_rate
        self.max_z = max_z
        self._channels: Dict[str, OnlineGaussian] = {}
        self._habituation: Dict[str, float] = {}

    def observe(self, channel: str, value: float, *,
                learn: bool = True, now: Optional[float] = None) -> SurpriseReading:
        if not math.isfinite(value):
            raise SurpriseError("value must be finite", context={"channel": channel, "value": repr(value)})
        now = time.time() if now is None else now
        stats = self._channels.setdefault(channel, OnlineGaussian())

        z = stats.z_score(value)
        z_capped = min(abs(z) if math.isfinite(z) else self.max_z, self.max_z)
        raw = z_capped / self.max_z  # normalise to [0, 1]

        habit = self._habituation.get(channel, 0.0)
        surprise = raw * (1.0 - habit)
        # habituation chases recent raw surprise
        self._habituation[channel] = habit + self.habituation_rate * (raw - habit)

        if learn:
            stats.update(value)

        return SurpriseReading(channel=channel, value=value, z=z,
                               surprise=surprise, habituation=self._habituation[channel],
                               timestamp=now)

    def observe_many(self, values: Mapping[str, float], *,
                     learn: bool = True) -> Dict[str, SurpriseReading]:
        return {ch: self.observe(ch, v, learn=learn) for ch, v in values.items()}

    def reset(self, channel: Optional[str] = None) -> None:
        if channel is None:
            self._channels.clear()
            self._habituation.clear()
        else:
            self._channels.pop(channel, None)
            self._habituation.pop(channel, None)

    def channels(self) -> Tuple[str, ...]:
        return tuple(sorted(self._channels))


class NoveltyGate:
    """Turns surprise scores into admit/suppress decisions."""

    def __init__(self, *, threshold: float = 0.35, cooldown_s: float = 5.0) -> None:
        if not 0.0 < threshold < 1.0:
            raise SurpriseError("threshold must be in (0, 1)", context={"threshold": threshold})
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._last_fire: Dict[str, float] = {}
        self.admitted: int = 0
        self.suppressed: int = 0

    def admit(self, reading: SurpriseReading) -> bool:
        if reading.surprise < self.threshold:
            self.suppressed += 1
            return False
        last = self._last_fire.get(reading.channel)
        if last is not None and reading.timestamp - last < self.cooldown_s:
            self.suppressed += 1
            return False
        self._last_fire[reading.channel] = reading.timestamp
        self.admitted += 1
        return True

    def report(self) -> Dict[str, int]:
        return {"admitted": self.admitted, "suppressed": self.suppressed}
