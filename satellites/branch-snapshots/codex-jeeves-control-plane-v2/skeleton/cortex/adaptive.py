"""Adaptive inference control plane for the pure-Python cortex.

The controller separates *what* compute to spend from the transformer itself.
It is deliberately model-agnostic: callers provide uncertainty/novelty/risk
signals and receive a bounded depth/width/verification plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class InferenceBudget:
    max_layers: int
    max_tokens: int
    max_verifiers: int = 1
    min_confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.max_layers < 1 or self.max_tokens < 1:
            raise ValueError("inference budgets must be positive")
        if self.max_verifiers < 0:
            raise ValueError("max_verifiers must be non-negative")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class InferencePlan:
    layers: int
    tokens: int
    verifiers: int
    confidence_target: float
    rationale: tuple[str, ...]

    @property
    def compute_units(self) -> int:
        return self.layers * self.tokens * (1 + self.verifiers)


class AdaptiveController:
    """Map uncertainty signals to a deterministic bounded compute plan."""

    def __init__(self, budget: InferenceBudget) -> None:
        self.budget = budget

    @staticmethod
    def _score(values: Iterable[float]) -> float:
        xs = [max(0.0, min(1.0, float(x))) for x in values]
        return sum(xs) / len(xs) if xs else 0.0

    def plan(
        self,
        *,
        uncertainty: float = 0.0,
        novelty: float = 0.0,
        risk: float = 0.0,
        confidence: float = 1.0,
        token_count: int = 1,
    ) -> InferencePlan:
        u = self._score((uncertainty, novelty, risk))
        confidence = max(0.0, min(1.0, float(confidence)))
        pressure = min(1.0, 0.55 * u + 0.45 * (1.0 - confidence))
        layers = 1 + int(round(pressure * (self.budget.max_layers - 1)))
        layers = min(self.budget.max_layers, max(1, layers))
        tokens = min(self.budget.max_tokens, max(1, int(token_count)))
        verifiers = min(self.budget.max_verifiers, int(risk >= 0.65 or confidence < self.budget.min_confidence))
        target = max(self.budget.min_confidence, min(1.0, confidence + pressure * 0.25))
        rationale: list[str] = []
        if uncertainty >= 0.5:
            rationale.append("uncertainty")
        if novelty >= 0.5:
            rationale.append("novelty")
        if risk >= 0.5:
            rationale.append("risk")
        if confidence < self.budget.min_confidence:
            rationale.append("confidence")
        if not rationale:
            rationale.append("baseline")
        return InferencePlan(layers, tokens, verifiers, target, tuple(rationale))


class EarlyExit:
    """Confidence-aware exit gate with a minimum depth guarantee."""

    def __init__(self, threshold: float = 0.9, min_layers: int = 1) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.threshold = threshold
        self.min_layers = max(1, int(min_layers))

    def should_stop(self, *, layer: int, confidence: float, stable: bool = True) -> bool:
        return layer >= self.min_layers and stable and float(confidence) >= self.threshold


__all__ = ["AdaptiveController", "EarlyExit", "InferenceBudget", "InferencePlan"]
