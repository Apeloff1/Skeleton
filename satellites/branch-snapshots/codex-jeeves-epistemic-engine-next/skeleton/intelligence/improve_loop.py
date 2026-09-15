"""Self-improvement loop — generate → verify → keep-if-better, bounded.

Direction-A research (frontier → production, 2026): AlphaEvolve-style
self-improvement — a generator proposes variants, an evaluator scores
them, the best survives — moved from research demos into production
prompt/policy tuning this year. The critical production lesson: the loop
must be *bounded and audited*, or it optimizes the metric into noise.

This engine is the minimal honest form: every iteration is recorded with
its score, the incumbent only changes on strict improvement, and the loop
halts on budget, patience (no-improvement streak), or target score.

Generator/evaluator are callables — pure domain, testable with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


GeneratorFn = Callable[[Any, int], Any]          # (incumbent, iteration) -> candidate
EvaluatorFn = Callable[[Any], float]             # candidate -> score (higher better)


@dataclass(frozen=True)
class Iteration:
    iteration: int
    score: float
    improved: bool


@dataclass
class ImproveResult:
    best: Any
    best_score: float
    iterations: List[Iteration] = field(default_factory=list)
    stopped_reason: str = "budget"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_score": round(self.best_score, 4),
            "iterations": [vars(i) for i in self.iterations],
            "stopped_reason": self.stopped_reason,
        }


class ImproveLoop:
    """Bounded generate-verify-keep loop with patience and audit trail."""

    def __init__(self, *, max_iterations: int = 10, patience: int = 3,
                 target: Optional[float] = None,
                 min_gain: float = 0.0) -> None:
        if max_iterations < 1 or patience < 1:
            raise ValueError("max_iterations and patience must be >= 1")
        self.max_iterations = max_iterations
        self.patience = patience
        self.target = target
        self.min_gain = min_gain
        self.runs = 0

    def run(self, seed: Any, generate: GeneratorFn,
            evaluate: EvaluatorFn) -> ImproveResult:
        """Improve on ``seed`` until budget, patience, or target stops us."""
        self.runs += 1
        best = seed
        best_score = evaluate(seed)
        result = ImproveResult(best=best, best_score=best_score)
        dry = 0
        for i in range(1, self.max_iterations + 1):
            candidate = generate(best, i)
            score = evaluate(candidate)
            improved = score > best_score + self.min_gain
            result.iterations.append(Iteration(i, score, improved))
            if improved:
                best, best_score = candidate, score
                result.best = best
                result.best_score = best_score
                dry = 0
            else:
                dry += 1
            if self.target is not None and best_score >= self.target:
                result.stopped_reason = "target"
                break
            if dry >= self.patience:
                result.stopped_reason = "patience"
                break
        else:
            result.stopped_reason = "budget"
        return result
