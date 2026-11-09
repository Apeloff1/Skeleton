"""Adaptive compute allocation for the neo cortex.

Mixture-of-Depths is deliberately independent from Mixture-of-Experts:
MoE selects *which* specialist acts; this module selects *how much* compute
is spent. The policy is deterministic, snapshotable, and safe to use as a
pure planning primitive before wiring it into the hot transformer path.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Sequence
import math


@dataclass(frozen=True)
class ComputeBudget:
    minimum: int = 1
    maximum: int = 4
    total: int = 16

    def normalized(self) -> "ComputeBudget":
        lo = max(0, int(self.minimum))
        hi = max(lo, int(self.maximum))
        return ComputeBudget(lo, hi, max(0, int(self.total)))


@dataclass(frozen=True)
class DepthDecision:
    depth: int
    halt: bool
    score: float
    reason: str


@dataclass
class DepthTrace:
    decisions: List[DepthDecision]
    consumed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"decisions": [asdict(x) for x in self.decisions], "consumed": self.consumed}


class DepthPolicy:
    """Budget-aware depth allocator using uncertainty, novelty and risk.

    Inputs are normalized to [0, 1]. The score is intentionally transparent:
    it can be audited, tuned, or replaced by a learned policy later.
    """

    def __init__(self, budget: ComputeBudget | None = None, *, uncertainty_weight: float = .45,
                 novelty_weight: float = .25, risk_weight: float = .30,
                 halt_threshold: float = .18) -> None:
        self.budget = (budget or ComputeBudget()).normalized()
        self.weights = (float(uncertainty_weight), float(novelty_weight), float(risk_weight))
        self.halt_threshold = float(halt_threshold)

    @staticmethod
    def _unit(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def score(self, *, uncertainty: float = 0.0, novelty: float = 0.0, risk: float = 0.0) -> float:
        u, n, r = map(self._unit, (uncertainty, novelty, risk))
        a, b, c = self.weights
        return max(0.0, min(1.0, a * u + b * n + c * r))

    def allocate(self, signals: Iterable[Dict[str, float]]) -> DepthTrace:
        rows = list(signals)
        budget = self.budget
        remaining = budget.total
        decisions: List[DepthDecision] = []
        for row in rows:
            s = self.score(uncertainty=row.get("uncertainty", 0), novelty=row.get("novelty", 0), risk=row.get("risk", 0))
            desired = budget.minimum + int(round(s * (budget.maximum - budget.minimum)))
            depth = min(desired, max(0, remaining))
            if depth < budget.minimum and remaining >= budget.minimum:
                depth = budget.minimum
            halt = depth == 0 or (s <= self.halt_threshold and depth <= budget.minimum)
            reason = "low-signal" if s <= self.halt_threshold else ("risk" if row.get("risk", 0) >= .7 else "adaptive")
            decisions.append(DepthDecision(depth=depth, halt=halt, score=s, reason=reason))
            remaining -= depth
        return DepthTrace(decisions=decisions, consumed=budget.total - remaining)

    def snapshot(self) -> Dict[str, Any]:
        return {"budget": asdict(self.budget), "weights": list(self.weights), "halt_threshold": self.halt_threshold}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "DepthPolicy":
        d = data or {}
        return cls(ComputeBudget(**(d.get("budget") or {})),
                   uncertainty_weight=(d.get("weights") or [.45, .25, .30])[0],
                   novelty_weight=(d.get("weights") or [.45, .25, .30])[1],
                   risk_weight=(d.get("weights") or [.45, .25, .30])[2],
                   halt_threshold=d.get("halt_threshold", .18))


def confidence_to_signals(confidence: float, *, novelty: float = 0.0, risk: float = 0.0) -> Dict[str, float]:
    """Bridge common confidence APIs into allocator signals."""
    c = max(0.0, min(1.0, float(confidence)))
    return {"uncertainty": 1.0 - c, "novelty": novelty, "risk": risk}
