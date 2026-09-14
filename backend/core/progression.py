"""Portable, defensive progression state mined from Hyperforge save semantics."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import math
from typing import Any


class Medal(IntEnum):
    NONE = 0
    BRONZE = 1
    SILVER = 2
    GOLD = 3
    ELITE = 4


@dataclass(frozen=True, slots=True)
class FinishResult:
    improved: bool
    medal_improved: bool
    newly_unlocked: tuple[str, ...]


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _medal(value: Any) -> Medal | None:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return Medal(number) if number in {item.value for item in Medal} else None


@dataclass(slots=True)
class ProgressionState:
    version: int = 1
    best: dict[str, float] = field(default_factory=dict)
    medals: dict[str, Medal] = field(default_factory=dict)
    ghosts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    total_distance: float = 0.0
    unlocked: set[str] = field(default_factory=set)

    @classmethod
    def migrate(cls, raw: dict[str, Any], *, initial_unlocks: set[str] | None = None) -> "ProgressionState":
        if not isinstance(raw, dict):
            raise ValueError("progression payload must be an object")
        state = cls(unlocked={str(item) for item in (initial_unlocks or set()) if str(item)})

        best_raw = raw.get("best") if isinstance(raw.get("best"), dict) else {}
        for key, value in best_raw.items():
            score = _finite_nonnegative(value)
            if score is not None and str(key):
                state.best[str(key)] = score

        medals_raw = raw.get("medals") if isinstance(raw.get("medals"), dict) else {}
        for key, value in medals_raw.items():
            medal = _medal(value)
            if medal is not None and str(key):
                state.medals[str(key)] = medal

        ghosts_raw = raw.get("ghosts") if isinstance(raw.get("ghosts"), dict) else {}
        for key, value in ghosts_raw.items():
            if not str(key) or not isinstance(value, list):
                continue
            samples = [dict(sample) for sample in value if isinstance(sample, dict)]
            state.ghosts[str(key)] = samples[:100_000]

        distance = _finite_nonnegative(raw.get("total_distance", 0.0))
        state.total_distance = distance if distance is not None else 0.0
        unlocked_raw = raw.get("unlocked") if isinstance(raw.get("unlocked"), (list, tuple, set)) else ()
        state.unlocked.update(str(value) for value in unlocked_raw if str(value))
        return state

    def record_finish(
        self,
        stage_id: str,
        *,
        score: float,
        medal: Medal,
        ghost: list[dict[str, Any]] | None = None,
        distance: float = 0.0,
        unlocks: dict[str, tuple[str, ...]] | None = None,
    ) -> FinishResult:
        if not stage_id:
            raise ValueError("stage_id is required")
        if not math.isfinite(score) or not math.isfinite(distance) or score < 0 or distance < 0:
            raise ValueError("score and distance must be finite and non-negative")
        previous = self.best.get(stage_id)
        improved = previous is None or score < previous
        current_medal = self.medals.get(stage_id, Medal.NONE)
        medal_improved = medal > current_medal
        if improved:
            self.best[stage_id] = score
            if ghost is not None:
                self.ghosts[stage_id] = [dict(sample) for sample in ghost if isinstance(sample, dict)][:100_000]
        if medal_improved:
            self.medals[stage_id] = medal
        self.total_distance += distance

        before = set(self.unlocked)
        if medal > Medal.NONE and unlocks:
            self.unlocked.update(unlocks.get(stage_id, ()))
        return FinishResult(
            improved=improved,
            medal_improved=medal_improved,
            newly_unlocked=tuple(sorted(self.unlocked - before)),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "best": dict(self.best),
            "medals": {key: int(value) for key, value in self.medals.items()},
            "ghosts": {key: list(value) for key, value in self.ghosts.items()},
            "total_distance": self.total_distance,
            "unlocked": sorted(self.unlocked),
        }
