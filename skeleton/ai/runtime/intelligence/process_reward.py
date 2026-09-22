"""Process rewards — score reasoning trajectories step by step, not just the ending.

Wave-4 SOTA (process-reward / step-verification line, e.g. AgentPRM's
promise+progress decomposition): outcome-only scoring rewards lucky paths
and punishes good work that ended badly. This module scores each *step*
on two axes:

- **promise** — does this step open useful continuations (new information,
  valid next actions)?
- **progress** — does it close distance to the goal vs the previous step?

Trajectory score aggregates steps (weighted mean, latest steps count more),
and ``select_best`` implements best-of-n by trajectory score rather than
outcome alone. Step scorers are injectable callables — pure domain, no
model required (a heuristic scorer ships as default for tests/CI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class StepScore:
    step_index: int
    promise: float
    progress: float
    note: str = ""

    @property
    def value(self) -> float:
        return 0.5 * self.promise + 0.5 * self.progress


StepScorer = Callable[[str, Optional[str], Dict[str, Any]], Tuple[float, float]]


def heuristic_step_scorer(step: str, prev: Optional[str], context: Dict[str, Any]) -> Tuple[float, float]:
    """Default scorer: lexical novelty as promise, length-normalized
    overlap-with-goal as progress. Deterministic; tests and CI use this."""
    words = set(step.lower().split())
    prev_words = set(prev.lower().split()) if prev else set()
    goal_words = set(str(context.get("goal", "")).lower().split())
    novelty = len(words - prev_words) / max(1, len(words))
    alignment = len(words & goal_words) / max(1, len(goal_words)) if goal_words else 0.5
    return round(min(1.0, novelty), 4), round(min(1.0, alignment), 4)


@dataclass
class Trajectory:
    steps: List[str] = field(default_factory=list)
    scores: List[StepScore] = field(default_factory=list)

    def aggregate(self, *, recency_weight: float = 0.7) -> float:
        """Recency-weighted mean of step values."""
        if not self.scores:
            return 0.0
        n = len(self.scores)
        weights = [recency_weight ** (n - 1 - i) for i in range(n)]
        total_w = sum(weights)
        return sum(s.value * w for s, w in zip(self.scores, weights)) / total_w


class ProcessRewarder:
    """Scores trajectories stepwise; selects best-of-n by process, not outcome."""

    def __init__(self, scorer: Optional[StepScorer] = None) -> None:
        self._scorer = scorer or heuristic_step_scorer

    def score_trajectory(self, steps: Sequence[str],
                         *, context: Optional[Dict[str, Any]] = None) -> Trajectory:
        ctx = dict(context or {})
        traj = Trajectory(steps=list(steps))
        prev: Optional[str] = None
        for i, step in enumerate(steps):
            promise, progress = self._scorer(step, prev, ctx)
            traj.scores.append(StepScore(i, promise, progress))
            prev = step
        return traj

    def select_best(self, trajectories: Sequence[Sequence[str]],
                    *, context: Optional[Dict[str, Any]] = None) -> Tuple[int, Trajectory]:
        """Best-of-n by aggregate process score. Deterministic tie-break by index."""
        if not trajectories:
            raise ValueError("select_best requires at least one trajectory")
        scored = [self.score_trajectory(t, context=context) for t in trajectories]
        best_idx = max(range(len(scored)), key=lambda i: (scored[i].aggregate(), -i))
        return best_idx, scored[best_idx]
