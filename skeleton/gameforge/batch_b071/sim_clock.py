"""B071 — Deterministic simulation clock.

Success criterion: "Game/system tests control time, entropy and ordering
explicitly."

* :class:`SimClock` — manual, integer-tick time; never reads the wall clock.
* :class:`DeterministicRng` — seeded entropy with forkable named streams so
  adding a consumer does not perturb other consumers' sequences.
* :class:`EventScheduler` — runs callbacks ordered by (tick, priority, seq),
  so ties are resolved explicitly rather than by insertion accident.
* :class:`SimContext` — bundles the three; ``snapshot()`` is hashable state.
"""
from __future__ import annotations

import hashlib
import heapq
import random
from dataclasses import dataclass, field
from typing import Callable, List, Tuple


MAX_SIM_TICK = (1 << 63) - 1
MAX_QUEUE_EVENTS = 100_000
MAX_EVENTS_PER_RUN = 100_000
MAX_EVENT_LOG = 100_000


class ClockError(ValueError):
    """Raised on illegal clock or scheduler operations."""


class SimClock:
    """Integer-tick clock. ``tick_ns`` converts ticks to nanoseconds."""

    def __init__(self, tick_ns: int = 16_666_667, start_tick: int = 0) -> None:
        if type(tick_ns) is not int or not 1 <= tick_ns <= 10**12:
            raise ClockError("tick_ns must be a bounded positive integer")
        if type(start_tick) is not int or not 0 <= start_tick <= MAX_SIM_TICK:
            raise ClockError("start_tick must be a bounded nonnegative integer")
        self.tick_ns = tick_ns
        self._tick = start_tick
        self._frozen = False

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def now_ns(self) -> int:
        return self._tick * self.tick_ns

    def advance(self, ticks: int = 1) -> int:
        if self._frozen:
            raise ClockError("clock is frozen")
        if type(ticks) is not int or ticks < 0:
            raise ClockError("time advance must be a nonnegative integer")
        if ticks > MAX_SIM_TICK - self._tick:
            raise ClockError("simulation tick exceeds bound")
        self._tick += ticks
        return self._tick

    def freeze(self) -> None:
        self._frozen = True

    def thaw(self) -> None:
        self._frozen = False


class DeterministicRng:
    """Seeded RNG; ``fork(name)`` derives an independent stream from seed+name."""

    def __init__(self, seed: int) -> None:
        if type(seed) is not int or not 0 <= seed <= MAX_SIM_TICK:
            raise ClockError("seed must be a bounded nonnegative integer")
        self.seed = seed
        self._rng = random.Random(seed)
        self.draws = 0

    def fork(self, name: str) -> "DeterministicRng":
        if type(name) is not str or not 1 <= len(name) <= 128:
            raise ClockError("RNG stream name must be a bounded string")
        h = hashlib.sha256(f"{self.seed}:{name}".encode()).digest()
        return DeterministicRng(int.from_bytes(h[:8], "big") & MAX_SIM_TICK)

    def randint(self, lo: int, hi: int) -> int:
        self.draws += 1
        return self._rng.randint(lo, hi)

    def random(self) -> float:
        self.draws += 1
        return self._rng.random()

    def choice(self, seq):
        if not seq:
            raise ClockError("choice from empty sequence")
        self.draws += 1
        return seq[self._rng.randrange(len(seq))]

    def shuffle(self, items: list) -> list:
        out = list(items)
        self.draws += 1
        self._rng.shuffle(out)
        return out


@dataclass(order=True)
class _Event:
    tick: int
    priority: int
    seq: int
    name: str = field(compare=False)
    fn: Callable[[], None] = field(compare=False)


class EventScheduler:
    """Explicitly ordered event queue bound to a :class:`SimClock`."""

    def __init__(self, clock: SimClock) -> None:
        self.clock = clock
        self._q: List[_Event] = []
        self._seq = 0
        self.log: List[Tuple[int, str]] = []

    def schedule(self, delay: int, name: str, fn: Callable[[], None], priority: int = 0) -> None:
        if type(delay) is not int or delay < 0:
            raise ClockError("delay must be a nonnegative integer")
        if type(priority) is not int or type(name) is not str or not 1 <= len(name) <= 128 or not callable(fn):
            raise ClockError("invalid scheduled event")
        if delay > MAX_SIM_TICK - self.clock.tick:
            raise ClockError("scheduled tick exceeds bound")
        if len(self._q) >= MAX_QUEUE_EVENTS:
            raise ClockError("scheduled event queue exceeds bound")
        heapq.heappush(self._q, _Event(self.clock.tick + delay, priority, self._seq, name, fn))
        self._seq += 1

    def pending(self) -> int:
        return len(self._q)

    def run_until(self, tick: int) -> int:
        if type(tick) is not int or not self.clock.tick <= tick <= MAX_SIM_TICK:
            raise ClockError("target tick is invalid or in the past")
        ran = 0
        while self._q and self._q[0].tick <= tick:
            if ran >= MAX_EVENTS_PER_RUN or len(self.log) >= MAX_EVENT_LOG:
                raise ClockError("simulation event run budget exceeded")
            ev = heapq.heappop(self._q)
            self.clock.advance(ev.tick - self.clock.tick)
            ev.fn()
            self.log.append((ev.tick, ev.name))
            ran += 1
        self.clock.advance(tick - self.clock.tick)
        return ran


class SimContext:
    """Clock + RNG + scheduler; all game-system tests should take one of these."""

    def __init__(self, seed: int, tick_ns: int = 16_666_667) -> None:
        self.clock = SimClock(tick_ns)
        self.rng = DeterministicRng(seed)
        self.scheduler = EventScheduler(self.clock)

    def snapshot(self) -> dict:
        return {"tick": self.clock.tick, "seed": self.rng.seed, "draws": self.rng.draws,
                "pending": self.scheduler.pending(), "log": list(self.scheduler.log)}

    def state_hash(self) -> str:
        return hashlib.sha256(repr(sorted(self.snapshot().items())).encode()).hexdigest()
