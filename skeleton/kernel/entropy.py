"""Entropy pool — gathered, whitened, health-gated randomness.

Chaos injection, Byzantine voting, stigmergic sampling, and MAML support-set
selection all consume randomness, and all of them currently call the global
PRNG — which makes runs hard to reproduce and impossible to audit. The
entropy pool centralises randomness as a kernel service:

  - **Sources** feed raw bytes (timing jitter, event-bus timing, host noise,
    caller-supplied seeds for tests).
  - **Whitening** folds raw bytes through SHA-256 in counter mode, so a weak
    source cannot bias output.
  - **Health gating** estimates min-entropy per source via a byte-frequency
    chi-squared check; sources below the floor are quarantined and the pool
    reports itself degraded instead of silently emitting weak randomness.

Seeded operation is deterministic, so tests and replayed runs get identical
streams — auditability is a feature, not a leak.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from skeleton.kernel.errors import KernelError


class EntropyError(KernelError):
    code = "KRN.ENTROPY"


@dataclass
class EntropySource:
    """A named randomness source with a health estimate."""
    name: str
    gather: Callable[[], bytes]
    samples: int = 0
    chi2_floor: float = 200.0     # below this, source is quarantined
    quarantined: bool = False
    last_chi2: float = 0.0

    def health_sample(self) -> float:
        """Chi-squared over byte distribution of a fresh gather."""
        data = self.gather()
        if len(data) < 32:
            self.last_chi2 = 0.0
            self.quarantined = True
            return 0.0
        freq = [0] * 256
        for b in data:
            freq[b] += 1
        expected = len(data) / 256
        chi2 = sum((f - expected) ** 2 / expected for f in freq)
        self.last_chi2 = chi2
        self.samples += 1
        # Suspiciously uniform is as bad as suspiciously skewed — real noise
        # sits in a band; we quarantine only obvious failure.
        if chi2 < self.chi2_floor:
            self.quarantined = True
        return chi2


class EntropyPool:
    """
    Kernel entropy service: source registry, whitening, health, generation.

    Parameters
    ----------
    seed:
        Optional deterministic seed. When set, every pool with the same seed
        and the same call sequence emits identical bytes.
    """

    def __init__(self, *, seed: Optional[int] = None) -> None:
        self._sources: Dict[str, EntropySource] = {}
        self._counter = 0
        self._state = hashlib.sha256(
            (str(seed) if seed is not None else repr(time.time_ns())).encode()
        ).digest()
        self._seeded = seed is not None
        self.bytes_generated = 0

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def add_source(self, source: EntropySource) -> None:
        self._sources[source.name] = source

    def add_timing_source(self, name: str = "timing") -> None:
        """Convenience: nanosecond clock jitter as a source."""
        self.add_source(EntropySource(
            name=name,
            gather=lambda: repr((time.time_ns(), time.perf_counter_ns())).encode(),
        ))

    def health_check(self) -> Dict[str, float]:
        """Sample every source; returns name → chi2. Quarantines failures."""
        return {name: s.health_sample() for name, s in self._sources.items()}

    @property
    def degraded(self) -> bool:
        live = [s for s in self._sources.values() if not s.quarantined]
        return bool(self._sources) and not live

    # ------------------------------------------------------------------
    # Mixing and generation
    # ------------------------------------------------------------------

    def _stir(self) -> None:
        """Fold live sources into the pool state."""
        h = hashlib.sha256(self._state)
        for source in self._sources.values():
            if not source.quarantined:
                h.update(source.gather())
        self._state = h.digest()

    def random_bytes(self, n: int) -> bytes:
        """n whitened bytes from the pool."""
        if n <= 0:
            raise EntropyError("random_bytes requires n > 0")
        if not self._seeded:
            self._stir()
        out = bytearray()
        while len(out) < n:
            self._counter += 1
            block = hashlib.sha256(self._state + self._counter.to_bytes(8, "big")).digest()
            out.extend(block)
        self.bytes_generated += n
        return bytes(out[:n])

    def randbelow(self, upper: int) -> int:
        """Unbiased integer in [0, upper) via rejection sampling."""
        if upper <= 0:
            raise EntropyError("randbelow requires upper > 0")
        span = 1 << (upper - 1).bit_length()
        while True:
            candidate = int.from_bytes(self.random_bytes(8), "big") % span
            if candidate < upper:
                return candidate

    def shuffle(self, items: list) -> None:
        """In-place Fisher–Yates with pool randomness."""
        for i in range(len(items) - 1, 0, -1):
            j = self.randbelow(i + 1)
            items[i], items[j] = items[j], items[i]

    def uniform(self) -> float:
        """Float in [0.0, 1.0)."""
        return int.from_bytes(self.random_bytes(8), "big") / 2**64

    def stats(self) -> Dict[str, object]:
        return {
            "sources": len(self._sources),
            "quarantined": sum(1 for s in self._sources.values() if s.quarantined),
            "seeded": self._seeded,
            "degraded": self.degraded,
            "bytes_generated": self.bytes_generated,
        }
