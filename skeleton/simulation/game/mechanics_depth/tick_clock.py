"""Explicit tick clock and seeded entropy — never process globals."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TickClock:
    """Monotonic integer tick. No wall-clock reads."""

    tick: int = 0
    max_tick: int = 1_000_000

    def advance(self, n: int = 1) -> int:
        if n < 1:
            raise ValueError("advance must be >= 1")
        nxt = self.tick + n
        if nxt > self.max_tick:
            raise ValueError("tick overflow")
        self.tick = nxt
        return self.tick

    def snapshot(self) -> int:
        return self.tick


@dataclass
class SeededEntropy:
    """Deterministic u64 stream from seed+tick; no random module."""

    seed: int
    _counter: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or self.seed < 0 or self.seed > 2_147_483_647:
            raise ValueError("seed out of range")

    def _next_digest(self) -> bytes:
        payload = f"{self.seed}:{self._counter}".encode()
        self._counter += 1
        return hashlib.sha256(payload).digest()

    def u64(self) -> int:
        return int.from_bytes(self._next_digest()[:8], "big")

    def unit(self) -> float:
        return (self.u64() % 10_000_000) / 10_000_000.0

    def choose(self, n: int) -> int:
        if n < 1:
            raise ValueError("n must be >= 1")
        return self.u64() % n

    def stream(self, count: int) -> Iterator[int]:
        for _ in range(count):
            yield self.u64()
