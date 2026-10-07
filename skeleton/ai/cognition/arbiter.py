"""Deterministic action arbitration across confidence, risk, value and cost."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True, slots=True)
class Candidate:
    action: str
    confidence: float
    value: float
    risk: float = 0.0
    cost: float = 1.0
    priority: int = 0

@dataclass(frozen=True, slots=True)
class Decision:
    action: str | None
    score: float
    rejected: tuple[str, ...]
    reason: str

class Arbiter:
    def __init__(self, *, risk_limit: float = 0.8, min_confidence: float = 0.0, budget: float = float("inf")) -> None:
        if not 0 <= risk_limit <= 1 or not 0 <= min_confidence <= 1 or budget < 0:
            raise ValueError("invalid arbitration limits")
        self.risk_limit, self.min_confidence, self.budget = risk_limit, min_confidence, float(budget)

    def decide(self, candidates: Iterable[Candidate]) -> Decision:
        ranked: list[tuple[float, Candidate]] = []
        rejected: list[str] = []
        for c in candidates:
            if not c.action or c.cost < 0 or c.risk > self.risk_limit or c.confidence < self.min_confidence or c.cost > self.budget:
                rejected.append(c.action)
                continue
            score = (0.45 * c.confidence + 0.35 * c.value + 0.20 * (1.0 - c.risk)) / (1.0 + c.cost)
            score += max(-1.0, min(1.0, c.priority)) * 0.001
            ranked.append((score, c))
        if not ranked:
            return Decision(None, 0.0, tuple(sorted(rejected)), "no_candidate_passed_gates")
        score, winner = max(ranked, key=lambda x: (x[0], x[1].priority, x[1].action))
        return Decision(winner.action, score, tuple(sorted(rejected)), "highest_utility")

__all__ = ["Arbiter", "Candidate", "Decision"]
