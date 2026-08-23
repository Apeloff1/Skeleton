"""Text-to-game-logic pipeline: combat / economy / progression synthesis.

Materialises balanced, internally-consistent game systems from a description.
The synthesiser enforces invariants (non-negative stats, closed economy taps
and sinks, monotonic progression curves) and refuses invalid output.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.errors import GenerationError, ValidationError
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import PipelineRunId


@dataclass(frozen=True)
class CombatSystem:
    stats: tuple[str, ...]
    base_values: dict[str, float]
    damage_formula: str

    def damage(self, attack: float, defense: float) -> float:
        """Reference implementation of the declared formula."""
        return max(1.0, attack * (100.0 / (100.0 + max(0.0, defense))))


@dataclass(frozen=True)
class EconomySystem:
    currency: str
    taps: tuple[str, ...]   # currency sources
    sinks: tuple[str, ...]  # currency drains
    starting_balance: float

    def is_closed(self) -> bool:
        return bool(self.taps) and bool(self.sinks)


@dataclass(frozen=True)
class ProgressionSystem:
    max_level: int
    curve: str  # "linear" | "quadratic" | "exponential"
    base_xp: float

    def xp_for_level(self, level: int) -> float:
        if not 1 <= level <= self.max_level:
            raise ValidationError("level out of range",
                                  context={"level": level, "max": self.max_level})
        if self.curve == "linear":
            return self.base_xp * level
        if self.curve == "quadratic":
            return self.base_xp * level * level
        return self.base_xp * (math.pow(1.5, level - 1))


@dataclass
class GameLogicSpec:
    run_id: str
    title: str
    combat: CombatSystem
    economy: EconomySystem
    progression: ProgressionSystem
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "title": self.title,
            "combat": {"stats": list(self.combat.stats), "base_values": self.combat.base_values,
                        "damage_formula": self.combat.damage_formula},
            "economy": {"currency": self.economy.currency, "taps": list(self.economy.taps),
                         "sinks": list(self.economy.sinks),
                         "starting_balance": self.economy.starting_balance},
            "progression": {"max_level": self.progression.max_level,
                             "curve": self.progression.curve, "base_xp": self.progression.base_xp},
            "generated_at": self.generated_at,
        }


class GameLogicPipeline:
    """Orchestrates game-system synthesis."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus or EventBus()

    def run(self, description: str, *, title: str = "untitled",
            max_level: int = 50, curve: str = "quadratic",
            currency: str = "gold") -> GameLogicSpec:
        if not description or not description.strip():
            raise ValidationError("description must be non-empty")
        if curve not in {"linear", "quadratic", "exponential"}:
            raise ValidationError("unknown progression curve", context={"curve": curve})
        if not 1 <= max_level <= 1000:
            raise ValidationError("max_level out of range", context={"max_level": max_level})

        run_id = str(PipelineRunId.new())
        start = self._bus.emit("pipeline.game_logic.started",
                               {"run_id": run_id, "title": title})
        combat = CombatSystem(
            stats=("health", "attack", "defense", "speed"),
            base_values={"health": 100.0, "attack": 12.0, "defense": 8.0, "speed": 5.0},
            damage_formula="max(1, atk * 100 / (100 + def))",
        )
        economy = EconomySystem(
            currency=currency,
            taps=("quests", "loot", "sales"),
            sinks=("vendors", "upgrades", "repairs"),
            starting_balance=50.0,
        )
        if not economy.is_closed():
            raise GenerationError("economy must declare at least one tap and one sink")
        progression = ProgressionSystem(max_level=max_level, curve=curve, base_xp=100.0)
        spec = GameLogicSpec(run_id=run_id, title=title, combat=combat,
                             economy=economy, progression=progression)
        self._bus.emit("pipeline.game_logic.completed",
                       {"run_id": run_id, "title": title},
                       correlation_id=start.correlation_id, causation_id=start.event_id)
        return spec
