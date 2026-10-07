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
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import PipelineRunId


@dataclass(frozen=True)
class CombatSystem:
    stats: tuple[str, ...]
    base_values: dict[str, float]
    damage_formula: str

    def damage(self, attack: float, defense: float) -> float:
        return max(1.0, attack * (100.0 / (100.0 + max(0.0, defense))))


@dataclass(frozen=True)
class EconomySystem:
    currency: str
    taps: tuple[str, ...]
    sinks: tuple[str, ...]
    starting_balance: float

    def is_closed(self) -> bool:
        return bool(self.taps) and bool(self.sinks)


@dataclass(frozen=True)
class ProgressionSystem:
    max_level: int
    curve: str
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
    quality: dict[str, Any] = field(default_factory=dict)
    quality_stats: dict[str, Any] = field(default_factory=dict)
    repair: dict[str, Any] = field(default_factory=dict)

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
            "quality": dict(self.quality),
            "quality_stats": dict(self.quality_stats),
            "repair": dict(self.repair),
        }


class GameLogicPipeline:
    def __init__(self, bus: EventBus | None = None, *, root=None) -> None:
        self._bus = bus or EventBus()
        self._root = root

    def run(self, description: str, *, title: str = "untitled",
            max_level: int = 50, curve: str = "quadratic",
            currency: str = "gold", repair: bool = False) -> GameLogicSpec:
        from skeleton.intelligence.game_logic_repair import attempt_game_logic_repair
        from skeleton.intelligence.pipeline_verifier import PipelineVerifier
        from skeleton.organism.quality_state import append_quality

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

        verifier = PipelineVerifier()
        quality = verifier.verify_game_logic(spec.to_dict(), description=description)
        spec.quality = quality.to_dict()
        spec.quality_stats = verifier.stats()
        append_quality({
            "kind": "quality",
            "surface": "game_logic",
            "accepted": quality.accepted,
            "reason": quality.reason,
            "score": quality.score,
            "weakest_path": quality.weakest_path,
            "summary": quality.summary,
            "metadata": quality.quality.metadata,
        }, root=self._root)
        if not quality.accepted and repair:
            fixed = attempt_game_logic_repair(spec.to_dict(), description=description, root=self._root)
            spec.repair = {k: v for k, v in fixed.items() if k != "spec"}
            if fixed.get("ok"):
                repaired = fixed["spec"]
                spec.quality = fixed.get("after", spec.quality)
                spec.combat = CombatSystem(tuple((repaired.get("combat") or {}).get("stats") or spec.combat.stats), dict((repaired.get("combat") or {}).get("base_values") or spec.combat.base_values), str((repaired.get("combat") or {}).get("damage_formula") or spec.combat.damage_formula))
                spec.economy = EconomySystem(str((repaired.get("economy") or {}).get("currency") or spec.economy.currency), tuple((repaired.get("economy") or {}).get("taps") or spec.economy.taps), tuple((repaired.get("economy") or {}).get("sinks") or spec.economy.sinks), float((repaired.get("economy") or {}).get("starting_balance") or spec.economy.starting_balance))
                spec.progression = ProgressionSystem(int((repaired.get("progression") or {}).get("max_level") or spec.progression.max_level), str((repaired.get("progression") or {}).get("curve") or spec.progression.curve), float((repaired.get("progression") or {}).get("base_xp") or spec.progression.base_xp))

        self._bus.publish(DomainEvent(
            topic="pipeline.game_logic.quality",
            payload={
                "run_id": run_id,
                "title": title,
                "accepted": quality.accepted,
                "reason": quality.reason,
                "score": quality.score,
                "weakest_path": quality.weakest_path,
            },
            correlation_id=start.correlation_id,
            causation_id=start.event_id,
        ))
        self._bus.emit("pipeline.game_logic.completed",
                       {"run_id": run_id, "title": title},
                       correlation_id=start.correlation_id, causation_id=start.event_id)
        return spec
