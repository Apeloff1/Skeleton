"""Forgetting curves for the memory trinity.

Not all memories deserve to live forever, and eviction by raw age alone
throws away memories that matter while keeping ones that don't. This
module scores each memory's *retrievability* with an Ebbinghaus-style
exponential decay, modulated by reinforcement:

- every recall strengthens the trace (spacing effect — each successful
  retrieval flattens the decay),
- importance and emotional salience act as multiplicative stabilisers,
- memories below the retention floor become eviction candidates for the
  episodic store, ordered weakest-first.

Pure functions over :class:`MemoryTrace` records; the episodic store
owns persistence, this module owns the maths. Zero dependencies.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Tuple

from ..kernel.errors import SkeletonError


class ForgettingError(SkeletonError):
    code = "MEM.FORGET"


# Half-life of an unreinforced trace, in seconds (default ~1 day).
DEFAULT_HALF_LIFE_S = 86_400.0
# Retrievability below this is an eviction candidate.
DEFAULT_RETENTION_FLOOR = 0.05
# Each reinforcement multiplies the half-life by this (spacing effect).
SPACING_FACTOR = 1.8
# Cap on effective half-life growth so immortal traces need real importance.
MAX_STABILITY = 64.0


@dataclass(frozen=True)
class MemoryTrace:
    """Decay bookkeeping for one memory."""

    memory_id: str
    created_at: float
    last_recalled_at: float
    recalls: int = 0
    importance: float = 0.5      # 0..1, set at write time
    salience: float = 0.5        # 0..1, emotional/novelty weight

    def stability(self) -> float:
        """Effective half-life multiplier from reinforcement + weight."""
        spacing = SPACING_FACTOR ** min(self.recalls, 20)
        weight = 1.0 + 2.0 * max(self.importance, 0.0) + max(self.salience, 0.0)
        return min(spacing * weight, MAX_STABILITY)


def retrievability(trace: MemoryTrace, now: Optional[float] = None) -> float:
    """Ebbinghaus retrievability R = exp(-t / (S * half_life))."""
    now = time.time() if now is None else now
    elapsed = max(0.0, now - trace.last_recalled_at)
    if elapsed == 0.0:
        return 1.0
    s = trace.stability()
    return math.exp(-elapsed / (s * DEFAULT_HALF_LIFE_S))


def reinforce(trace: MemoryTrace, now: Optional[float] = None) -> MemoryTrace:
    """Record a successful recall — flattens the decay curve."""
    now = time.time() if now is None else now
    return replace(trace, last_recalled_at=now, recalls=trace.recalls + 1)


@dataclass(frozen=True)
class EvictionCandidate:
    memory_id: str
    retrievability: float
    age_s: float
    recalls: int


class ForgettingCurve:
    """Tracks traces for a store and answers "what may we forget?"."""

    def __init__(
        self,
        *,
        retention_floor: float = DEFAULT_RETENTION_FLOOR,
        half_life_s: float = DEFAULT_HALF_LIFE_S,
    ) -> None:
        if not 0.0 < retention_floor < 1.0:
            raise ForgettingError(
                "retention floor must be in (0, 1)",
                context={"retention_floor": retention_floor},
            )
        self.retention_floor = retention_floor
        self.half_life_s = half_life_s
        self._traces: Dict[str, MemoryTrace] = {}

    def register(self, memory_id: str, *, importance: float = 0.5,
                 salience: float = 0.5, now: Optional[float] = None) -> MemoryTrace:
        now = time.time() if now is None else now
        trace = MemoryTrace(
            memory_id=memory_id,
            created_at=now,
            last_recalled_at=now,
            importance=min(max(importance, 0.0), 1.0),
            salience=min(max(salience, 0.0), 1.0),
        )
        self._traces[memory_id] = trace
        return trace

    def on_recall(self, memory_id: str, now: Optional[float] = None) -> MemoryTrace:
        trace = self._traces.get(memory_id)
        if trace is None:
            raise ForgettingError(
                "recall for unregistered memory",
                context={"memory_id": memory_id},
            )
        trace = reinforce(trace, now)
        self._traces[memory_id] = trace
        return trace

    def score(self, memory_id: str, now: Optional[float] = None) -> float:
        trace = self._traces.get(memory_id)
        if trace is None:
            return 0.0
        return retrievability(trace, now)

    def eviction_candidates(self, now: Optional[float] = None,
                            limit: Optional[int] = None) -> List[EvictionCandidate]:
        now = time.time() if now is None else now
        doomed = [
            EvictionCandidate(
                memory_id=t.memory_id,
                retrievability=retrievability(t, now),
                age_s=now - t.created_at,
                recalls=t.recalls,
            )
            for t in self._traces.values()
            if retrievability(t, now) < self.retention_floor
        ]
        doomed.sort(key=lambda c: (c.retrievability, -c.age_s))
        return doomed[:limit] if limit else doomed

    def sweep(self, now: Optional[float] = None) -> Tuple[str, ...]:
        """Drop every sub-floor trace; returns the evicted ids."""
        now = time.time() if now is None else now
        doomed = {c.memory_id for c in self.eviction_candidates(now)}
        for mid in doomed:
            del self._traces[mid]
        return tuple(sorted(doomed))

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {
            mid: {
                "retrievability": retrievability(t),
                "recalls": float(t.recalls),
                "stability": t.stability(),
            }
            for mid, t in self._traces.items()
        }

    def __len__(self) -> int:
        return len(self._traces)
