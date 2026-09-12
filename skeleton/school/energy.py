"""Cognitive-energy budgeting mined from Newfix's energy model.

The source tracks game stamina, regeneration and boosters. For school, the
useful abstraction is a bounded cognitive budget: sessions consume budget,
recovery restores it, and low budget changes the teaching strategy rather than
simply blocking learning.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EnergyStrategy(str, Enum):
    DEEP_WORK = "deep_work"
    NORMAL = "normal"
    LIGHT_REVIEW = "light_review"
    REFLECTION = "reflection"
    STOP_AND_RECOVER = "stop_and_recover"


@dataclass(frozen=True)
class EnergyBudget:
    current: float = 1.0
    maximum: float = 1.0
    regeneration_per_hour: float = 0.1

    def validate(self) -> None:
        if self.maximum <= 0:
            raise ValueError("maximum energy must be positive")
        if not 0 <= self.current <= self.maximum:
            raise ValueError("current energy must be within the budget")
        if self.regeneration_per_hour < 0:
            raise ValueError("regeneration rate cannot be negative")

    def consume(self, amount: float) -> "EnergyBudget":
        self.validate()
        if amount < 0:
            raise ValueError("energy cost cannot be negative")
        return EnergyBudget(max(0.0, self.current - amount), self.maximum, self.regeneration_per_hour)

    def recover(self, hours: float) -> "EnergyBudget":
        self.validate()
        if hours < 0:
            raise ValueError("recovery time cannot be negative")
        return EnergyBudget(min(self.maximum, self.current + hours * self.regeneration_per_hour), self.maximum, self.regeneration_per_hour)


@dataclass(frozen=True)
class EnergyDecision:
    strategy: EnergyStrategy
    session_minutes: int
    difficulty_multiplier: float
    rationale: tuple[str, ...]


def choose_energy_strategy(budget: EnergyBudget, *, requested_minutes: int = 45, high_cognitive_load: bool = False) -> EnergyDecision:
    budget.validate()
    ratio = budget.current / budget.maximum
    if ratio < 0.15:
        return EnergyDecision(EnergyStrategy.STOP_AND_RECOVER, 10, 0.7, ("cognitive budget is critically low",))
    if ratio < 0.35:
        strategy = EnergyStrategy.REFLECTION if high_cognitive_load else EnergyStrategy.LIGHT_REVIEW
        return EnergyDecision(strategy, min(20, requested_minutes), 0.75, ("cognitive budget is low", "prefer retrieval, reflection, or small wins"))
    if ratio < 0.65 or high_cognitive_load:
        return EnergyDecision(EnergyStrategy.NORMAL, min(30, requested_minutes), 0.9, ("reserve budget for sustained reasoning",))
    return EnergyDecision(EnergyStrategy.DEEP_WORK, requested_minutes, 1.0, ("sufficient budget for sustained practice",))
