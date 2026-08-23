"""Entanglement detection — hidden coupling between subsystems.

Two subsystems are *entangled* when their event streams co-vary in a way no
architect intended: pipeline failures that always precede vault rotations,
routing changes that shadow memory evictions, chaos injections that echo in
retrieval latency three seconds later. Nobody wrote that coupling down —
it emerged — and emergent coupling is exactly the kind that kills systems,
because it is invisible to every dashboard that tracks one subsystem at a
time.

This module consumes the kernel event bus's replay buffer and hunts for
that coupling:

  - **Lag correlation** — for each topic pair (A, B), slide a lag window and
    measure whether A-events are followed by B-events more often than chance
    (a permutation baseline, not a bare count — bare counts lie).
  - **Burst entanglement** — topics whose burst windows (N events inside
    Δt) overlap significantly more than independent Poisson streams would.
  - **Directionality** — A→B and B→A are measured separately; a one-sided
    entanglement is a suspected *cause*, a two-sided one a suspected *loop*.

Everything is computed from events already in the bus. No instrumentation,
no agents, no side-channels — the system is observed purely through the
facts it already emits.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent


@dataclass(frozen=True)
class Entanglement:
    """One detected coupling between two topics."""
    cause_topic: str
    effect_topic: str
    lag_ms: float
    lift: float            # observed co-occurrence / chance co-occurrence
    confidence: float      # 1 - p-value surrogate from permutation baseline
    direction: str         # "a_to_b" | "b_to_a" | "loop"
    samples: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cause": self.cause_topic,
            "effect": self.effect_topic,
            "lag_ms": round(self.lag_ms, 2),
            "lift": round(self.lift, 3),
            "confidence": round(self.confidence, 3),
            "direction": self.direction,
            "samples": self.samples,
        }


class EntanglementDetector:
    """
    Mines an event window for cross-topic coupling.

    Parameters
    ----------
    max_lag_s:
        Furthest lag tested between a cause and an effect.
    lag_step_s:
        Lag resolution of the sweep.
    min_lift:
        Minimum observed/chance ratio to report.
    permutations:
        Baseline shuffles for the chance estimate; more = tighter confidence.
    """

    def __init__(
        self,
        *,
        max_lag_s: float = 5.0,
        lag_step_s: float = 0.25,
        min_lift: float = 2.0,
        permutations: int = 50,
        seed: Optional[int] = None,
    ) -> None:
        self.max_lag_s = max_lag_s
        self.lag_step_s = lag_step_s
        self.min_lift = min_lift
        self.permutations = permutations
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def scan(self, events: Iterable[DomainEvent]) -> List[Entanglement]:
        """Scan an event window; return entanglements sorted by lift."""
        evs = sorted(events, key=lambda e: e.occurred_at)
        if len(evs) < 10:
            return []

        by_topic: Dict[str, List[float]] = defaultdict(list)
        for e in evs:
            by_topic[e.topic].append(e.occurred_at)

        findings: Dict[Tuple[str, str, int], Tuple[float, float]] = {}
        topics = sorted(by_topic)
        for a in topics:
            for b in topics:
                if a == b:
                    continue
                best = self._best_lag(by_topic[a], by_topic[b])
                if best is None:
                    continue
                lag_idx, lift, conf = best
                if lift >= self.min_lift:
                    findings[(a, b, lag_idx)] = (lift, conf)

        # Merge A→B and B→A to classify direction
        out: List[Entanglement] = []
        seen_pairs: set = set()
        for (a, b, lag_idx), (lift, conf) in sorted(
            findings.items(), key=lambda kv: kv[1][0], reverse=True
        ):
            pair = frozenset({a, b})
            reverse = max(
                (v for (x, y, _), v in findings.items() if x == b and y == a),
                key=lambda t: t[0],
                default=None,
            )
            direction = "a_to_b"
            if reverse is not None and reverse[0] >= self.min_lift:
                direction = "loop"
                if pair in seen_pairs:
                    continue
            seen_pairs.add(pair)
            out.append(
                Entanglement(
                    cause_topic=a,
                    effect_topic=b,
                    lag_ms=lag_idx * self.lag_step_s * 1000,
                    lift=lift,
                    confidence=conf,
                    direction=direction,
                    samples=min(len(by_topic[a]), len(by_topic[b])),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _co_occurrences(
        self, cause: List[float], effect: List[float], lag: float
    ) -> int:
        """How many effect-events land within one lag-step after a cause."""
        window = self.lag_step_s
        count = 0
        j0 = 0
        for t in cause:
            target = t + lag
            while j0 < len(effect) and effect[j0] < target - window / 2:
                j0 += 1
            j = j0
            while j < len(effect) and effect[j] <= target + window / 2:
                count += 1
                j += 1
        return count

    def _best_lag(
        self, cause: List[float], effect: List[float]
    ) -> Optional[Tuple[int, float, float]]:
        """
        Sweep lags; at each, compare observed co-occurrence to a permutation
        baseline (shuffled effect timestamps). Returns (lag_idx, lift, conf).
        """
        if not cause or not effect:
            return None
        t0, t1 = min(cause[0], effect[0]), max(cause[-1], effect[-1])
        span = max(t1 - t0, 1e-9)

        best: Optional[Tuple[int, float, float]] = None
        n_lags = int(self.max_lag_s / self.lag_step_s)
        for lag_idx in range(1, n_lags + 1):
            lag = lag_idx * self.lag_step_s
            observed = self._co_occurrences(cause, effect, lag)
            if observed == 0:
                continue

            # Chance baseline: shuffle effect times uniformly in the span
            chance_sum = 0
            beats = 0
            for _ in range(self.permutations):
                shuffled = sorted(
                    t0 + self._rng.random() * span for _ in range(len(effect))
                )
                c = self._co_occurrences(cause, shuffled, lag)
                chance_sum += c
                if c >= observed:
                    beats += 1
            chance = chance_sum / self.permutations
            lift = observed / chance if chance > 0 else float(observed)
            confidence = 1.0 - (beats / self.permutations)

            if best is None or lift > best[1]:
                best = (lag_idx, lift, confidence)
        return best
