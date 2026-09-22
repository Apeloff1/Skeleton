"""Deterministic progression ladder."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from skeleton.game.mechanics_depth.tick_clock import SeededEntropy, TickClock

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


def prestige_mult_0(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 0)) * (1.0 + 0 * 0.01)


def milestone_xp_0(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 0


def prestige_mult_1(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 1)) * (1.0 + 1 * 0.01)


def milestone_xp_1(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 3


def prestige_mult_2(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 2)) * (1.0 + 2 * 0.01)


def milestone_xp_2(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 6


def prestige_mult_3(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 3)) * (1.0 + 3 * 0.01)


def milestone_xp_3(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 9


def prestige_mult_4(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 4)) * (1.0 + 4 * 0.01)


def milestone_xp_4(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 12


def prestige_mult_5(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 5)) * (1.0 + 5 * 0.01)


def milestone_xp_5(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 15


def prestige_mult_6(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 6)) * (1.0 + 6 * 0.01)


def milestone_xp_6(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 18


def prestige_mult_7(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 7)) * (1.0 + 7 * 0.01)


def milestone_xp_7(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 21


def prestige_mult_8(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 8)) * (1.0 + 8 * 0.01)


def milestone_xp_8(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 24


def prestige_mult_9(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 9)) * (1.0 + 9 * 0.01)


def milestone_xp_9(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 27


def prestige_mult_10(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 10)) * (1.0 + 10 * 0.01)


def milestone_xp_10(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 30


def prestige_mult_11(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 11)) * (1.0 + 11 * 0.01)


def milestone_xp_11(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 33


def prestige_mult_12(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 12)) * (1.0 + 12 * 0.01)


def milestone_xp_12(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 36


def prestige_mult_13(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 13)) * (1.0 + 13 * 0.01)


def milestone_xp_13(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 39


def prestige_mult_14(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 14)) * (1.0 + 14 * 0.01)


def milestone_xp_14(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 42


def prestige_mult_15(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 15)) * (1.0 + 15 * 0.01)


def milestone_xp_15(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 45


def prestige_mult_16(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 16)) * (1.0 + 16 * 0.01)


def milestone_xp_16(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 48


def prestige_mult_17(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 17)) * (1.0 + 17 * 0.01)


def milestone_xp_17(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 51


def prestige_mult_18(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 18)) * (1.0 + 18 * 0.01)


def milestone_xp_18(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 54


def prestige_mult_19(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 19)) * (1.0 + 19 * 0.01)


def milestone_xp_19(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 57


def prestige_mult_20(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 20)) * (1.0 + 20 * 0.01)


def milestone_xp_20(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 60


def prestige_mult_21(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 21)) * (1.0 + 21 * 0.01)


def milestone_xp_21(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 63


def prestige_mult_22(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 22)) * (1.0 + 22 * 0.01)


def milestone_xp_22(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 66


def prestige_mult_23(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 23)) * (1.0 + 23 * 0.01)


def milestone_xp_23(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 69


def prestige_mult_24(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 24)) * (1.0 + 24 * 0.01)


def milestone_xp_24(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 72


def prestige_mult_25(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 25)) * (1.0 + 25 * 0.01)


def milestone_xp_25(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 75


def prestige_mult_26(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 26)) * (1.0 + 26 * 0.01)


def milestone_xp_26(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 78


def prestige_mult_27(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 27)) * (1.0 + 27 * 0.01)


def milestone_xp_27(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 81


def prestige_mult_28(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 28)) * (1.0 + 28 * 0.01)


def milestone_xp_28(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 84


def prestige_mult_29(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 29)) * (1.0 + 29 * 0.01)


def milestone_xp_29(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 87


def prestige_mult_30(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 30)) * (1.0 + 30 * 0.01)


def milestone_xp_30(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 90


def prestige_mult_31(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 31)) * (1.0 + 31 * 0.01)


def milestone_xp_31(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 93


def prestige_mult_32(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 32)) * (1.0 + 32 * 0.01)


def milestone_xp_32(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 96


def prestige_mult_33(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 33)) * (1.0 + 33 * 0.01)


def milestone_xp_33(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 99


def prestige_mult_34(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 34)) * (1.0 + 34 * 0.01)


def milestone_xp_34(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 102


def prestige_mult_35(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 35)) * (1.0 + 35 * 0.01)


def milestone_xp_35(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 105


def prestige_mult_36(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 36)) * (1.0 + 36 * 0.01)


def milestone_xp_36(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 108


def prestige_mult_37(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 37)) * (1.0 + 37 * 0.01)


def milestone_xp_37(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 111


def prestige_mult_38(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 38)) * (1.0 + 38 * 0.01)


def milestone_xp_38(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 114


def prestige_mult_39(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 39)) * (1.0 + 39 * 0.01)


def milestone_xp_39(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 117


def prestige_mult_40(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 40)) * (1.0 + 40 * 0.01)


def milestone_xp_40(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 120


def prestige_mult_41(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 41)) * (1.0 + 41 * 0.01)


def milestone_xp_41(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 123


def prestige_mult_42(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 42)) * (1.0 + 42 * 0.01)


def milestone_xp_42(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 126


def prestige_mult_43(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 43)) * (1.0 + 43 * 0.01)


def milestone_xp_43(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 129


def prestige_mult_44(level: int) -> float:
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError("level")
    return 1.0 + (level / (100.0 + 44)) * (1.0 + 44 * 0.01)


def milestone_xp_44(stage: int) -> int:
    if stage < 0 or stage > 100:
        raise ValueError("stage")
    return 50 * (stage + 1) * (stage + 2) + 132
