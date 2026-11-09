"""Deterministic progression ladder."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from skeleton.simulation.game.mechanics_depth.tick_clock import SeededEntropy, TickClock

MAX_LEVEL = 1000
MAX_XP = 1_000_000_000


@dataclass(frozen=True)
class LevelEvent:
    tick: int
    actor: str
    xp_gained: int
    level_before: int
    level_after: int
    leveled: bool

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()


def xp_to_next(level: int) -> int:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 100 + level * level * 5


class ProgressionLadder:
    def __init__(self, seed: int, *, clock: Optional[TickClock] = None) -> None:
        self.clock = clock or TickClock()
        self.entropy = SeededEntropy(seed)
        self._xp: Dict[str, int] = {}
        self._level: Dict[str, int] = {}
        self._events: List[LevelEvent] = []

    def enroll(self, actor: str, level: int = 1) -> None:
        if actor in self._xp:
            raise ValueError("enrolled")
        if not 1 <= level <= MAX_LEVEL:
            raise ValueError("level")
        self._level[actor] = level
        self._xp[actor] = 0

    def award(self, actor: str, xp: int) -> LevelEvent:
        if actor not in self._xp:
            raise KeyError(actor)
        if not 0 < xp <= MAX_XP:
            raise ValueError("xp")
        before = self._level[actor]
        self._xp[actor] += xp
        leveled = False
        while self._level[actor] < MAX_LEVEL and self._xp[actor] >= xp_to_next(self._level[actor]):
            self._xp[actor] -= xp_to_next(self._level[actor])
            self._level[actor] += 1
            leveled = True
        tick = self.clock.advance()
        ev = LevelEvent(tick, actor, xp, before, self._level[actor], leveled)
        self._events.append(ev)
        return ev

    def digest(self) -> str:
        body = json.dumps({"levels": self._level, "xp": self._xp}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()
