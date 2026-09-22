"""Deterministic ensemble aggregation for multiple candidate predictions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Hashable, Iterable

@dataclass(frozen=True, slots=True)
class Vote:
    value: Hashable
    confidence: float = 1.0
    weight: float = 1.0

@dataclass(frozen=True, slots=True)
class EnsembleResult:
    value: Hashable | None
    confidence: float
    support: int
    total: int

class Ensemble:
    def combine(self, votes: Iterable[Vote]) -> EnsembleResult:
        scores: dict[Hashable, float] = {}
        counts: dict[Hashable, int] = {}
        total = 0
        for vote in votes:
            if vote.weight < 0:
                continue
            total += 1
            confidence = max(0.0, min(1.0, float(vote.confidence)))
            scores[vote.value] = scores.get(vote.value, 0.0) + confidence * float(vote.weight)
            counts[vote.value] = counts.get(vote.value, 0) + 1
        if not scores:
            return EnsembleResult(None, 0.0, 0, total)
        winner = max(scores, key=lambda key: (scores[key], counts[key], repr(key)))
        denom = sum(scores.values())
        return EnsembleResult(winner, scores[winner] / denom if denom else 0.0, counts[winner], total)

__all__ = ["Ensemble", "EnsembleResult", "Vote"]
