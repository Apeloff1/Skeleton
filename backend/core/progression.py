"""Portable progression state mined from Hyperforge cockpit save semantics.

The original prototype coupled best times, medals, ghosts and course unlocks to
localStorage. This version keeps the valuable domain rules storage-neutral so
playables can persist them through any repository adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
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
        state = cls(unlocked=set(initial_unlocks or ()))
        state.version = 1
        state.best = {str(k): float(v) for k, v in dict(raw.get("best") or {}).items() if float(v) >= 0}
        state.medals = {
            str(k): Medal(int(v))
            for k, v in dict(raw.get("medals") or {}).items()
            if int(v) in {m.value for m in Medal}
        }
        state.ghosts = {str(k): list(v) for k, v in dict(raw.get("ghosts") or {}).items()}
        state.total_distance = max(0.0, float(raw.get("total_distance") or 0.0))
        supplied = {str(v) for v in (raw.get("unlocked") or []) if str(v)}
        state.unlocked |= supplied
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
        if score < 0 or distance < 0:
            raise ValueError("score and distance cannot be negative")
        previous = self.best.get(stage_id)
        improved = previous is None or score < previous
        current_medal = self.medals.get(stage_id, Medal.NONE)
        medal_improved = medal > current_medal
        if improved:
            self.best[stage_id] = score
            if ghost is not None:
                self.ghosts[stage_id] = list(ghost)
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
