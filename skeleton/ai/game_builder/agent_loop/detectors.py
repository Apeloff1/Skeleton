"""Win/loss detection over read-only snapshots."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable

from .state import GameSnapshot


class Outcome(str, enum.Enum):
    ONGOING = "ongoing"
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"


@dataclass(frozen=True)
class Rule:
    name: str
    outcome: Outcome
    predicate: Callable[[GameSnapshot], bool]


@dataclass
class WinLossDetector:
    """Evaluates rules in order. Loss rules take precedence over win rules when
    both fire on the same snapshot (conservative); ``max_turns`` yields DRAW."""
    rules: list[Rule] = field(default_factory=list)
    max_turns: int | None = None
    turn_key: str = "turn"

    def evaluate(self, snap: GameSnapshot) -> tuple[Outcome, str]:
        fired: list[Rule] = []
        for rule in self.rules:
            try:
                if rule.predicate(snap):
                    fired.append(rule)
            except Exception:
                continue  # a broken rule never decides the game
        for wanted in (Outcome.LOSS, Outcome.WIN, Outcome.DRAW):
            for rule in fired:
                if rule.outcome is wanted:
                    return wanted, rule.name
        if self.max_turns is not None and int(snap.get(self.turn_key, 0)) >= self.max_turns:
            return Outcome.DRAW, "max_turns"
        return Outcome.ONGOING, ""

    @classmethod
    def threshold(cls, key: str, win_at: float | None = None, lose_at: float | None = None,
                  max_turns: int | None = None) -> "WinLossDetector":
        rules: list[Rule] = []
        if lose_at is not None:
            rules.append(Rule(f"{key}<={lose_at}", Outcome.LOSS, lambda s: s.get(key, 0) <= lose_at))
        if win_at is not None:
            rules.append(Rule(f"{key}>={win_at}", Outcome.WIN, lambda s: s.get(key, 0) >= win_at))
        return cls(rules=rules, max_turns=max_turns)
