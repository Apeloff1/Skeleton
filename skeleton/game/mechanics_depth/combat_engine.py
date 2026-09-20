"""Deterministic combat engine for B021.

Frame-based strikes with seeded entropy. Same seed+tick → same StrikeResult.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.game.mechanics_depth.tick_clock import SeededEntropy, TickClock

MAX_HP = 10_000
MAX_DAMAGE = 10_000
MAX_ACTORS = 32
MAX_FRAMES = 256


@dataclass(frozen=True)
class CombatFrame:
    tick: int
    attacker: str
    defender: str
    raw_roll: float
    damage: int
    defender_hp_after: int
    fatal: bool

    def digest(self) -> str:
        body = json.dumps(
            {
                "tick": self.tick,
                "attacker": self.attacker,
                "defender": self.defender,
                "raw_roll": round(self.raw_roll, 6),
                "damage": self.damage,
                "hp": self.defender_hp_after,
                "fatal": self.fatal,
            },
            sort_keys=True,
        )
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class StrikeResult:
    frames: Tuple[CombatFrame, ...]
    winner: Optional[str]
    digest: str


@dataclass
class _Actor:
    name: str
    hp: int
    atk: int
    defense: int
    crit: float


class CombatEngine:
    """Multi-frame deterministic duel / skirmish simulator."""

    def __init__(self, seed: int, *, clock: Optional[TickClock] = None) -> None:
        self.clock = clock or TickClock()
        self.entropy = SeededEntropy(seed)
        self._actors: Dict[str, _Actor] = {}
        self._log: List[CombatFrame] = []

    def spawn(self, name: str, *, hp: int = 100, atk: int = 10, defense: int = 2, crit: float = 0.1) -> None:
        if len(self._actors) >= MAX_ACTORS:
            raise ValueError("actor cap")
        if not name or len(name) > 64:
            raise ValueError("bad name")
        if not (1 <= hp <= MAX_HP and 0 <= atk <= 500 and 0 <= defense <= 200):
            raise ValueError("stat bounds")
        if not 0.0 <= crit <= 1.0:
            raise ValueError("crit bounds")
        self._actors[name] = _Actor(name, hp, atk, defense, crit)

    def strike(self, attacker: str, defender: str) -> CombatFrame:
        if attacker not in self._actors or defender not in self._actors:
            raise KeyError("unknown actor")
        if attacker == defender:
            raise ValueError("cannot strike self")
        a, d = self._actors[attacker], self._actors[defender]
        if d.hp <= 0 or a.hp <= 0:
            raise ValueError("actor down")
        tick = self.clock.advance()
        roll = self.entropy.unit()
        base = max(0, a.atk - d.defense)
        crit_hit = roll < a.crit
        damage = min(MAX_DAMAGE, base * (2 if crit_hit else 1) + int(roll * 3))
        d.hp = max(0, d.hp - damage)
        frame = CombatFrame(tick, attacker, defender, roll, damage, d.hp, d.hp == 0)
        self._log.append(frame)
        if len(self._log) > MAX_FRAMES:
            self._log = self._log[-MAX_FRAMES:]
        return frame

    def duel(self, a: str, b: str, *, max_rounds: int = 64) -> StrikeResult:
        frames: List[CombatFrame] = []
        for i in range(max_rounds):
            if self._actors[a].hp <= 0 or self._actors[b].hp <= 0:
                break
            atk, dfn = (a, b) if i % 2 == 0 else (b, a)
            if self._actors[atk].hp <= 0:
                continue
            frames.append(self.strike(atk, dfn))
        winner = None
        if self._actors[a].hp <= 0 and self._actors[b].hp > 0:
            winner = b
        elif self._actors[b].hp <= 0 and self._actors[a].hp > 0:
            winner = a
        digest = hashlib.sha256("".join(f.digest() for f in frames).encode()).hexdigest()
        return StrikeResult(tuple(frames), winner, digest)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "tick": self.clock.tick,
            "actors": {n: {"hp": a.hp, "atk": a.atk, "defense": a.defense, "crit": a.crit} for n, a in self._actors.items()},
            "log_len": len(self._log),
        }


def combat_table_0(seed: int, n: int = 8) -> List[int]:
    """Lookup table 0 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 0)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 0))
    return out


def scale_damage_0(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 0)


def combat_table_1(seed: int, n: int = 8) -> List[int]:
    """Lookup table 1 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 9973)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 1))
    return out


def scale_damage_1(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 1)


def combat_table_2(seed: int, n: int = 8) -> List[int]:
    """Lookup table 2 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 19946)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 2))
    return out


def scale_damage_2(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 2)


def combat_table_3(seed: int, n: int = 8) -> List[int]:
    """Lookup table 3 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 29919)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 3))
    return out


def scale_damage_3(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 3)


def combat_table_4(seed: int, n: int = 8) -> List[int]:
    """Lookup table 4 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 39892)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 4))
    return out


def scale_damage_4(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 4)


def combat_table_5(seed: int, n: int = 8) -> List[int]:
    """Lookup table 5 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 49865)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 5))
    return out


def scale_damage_5(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 5)


def combat_table_6(seed: int, n: int = 8) -> List[int]:
    """Lookup table 6 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 59838)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 6))
    return out


def scale_damage_6(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 6)


def combat_table_7(seed: int, n: int = 8) -> List[int]:
    """Lookup table 7 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 69811)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 7))
    return out


def scale_damage_7(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 0)


def combat_table_8(seed: int, n: int = 8) -> List[int]:
    """Lookup table 8 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 79784)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 8))
    return out


def scale_damage_8(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 1)


def combat_table_9(seed: int, n: int = 8) -> List[int]:
    """Lookup table 9 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 89757)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 9))
    return out


def scale_damage_9(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 2)


def combat_table_10(seed: int, n: int = 8) -> List[int]:
    """Lookup table 10 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 99730)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 10))
    return out


def scale_damage_10(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 3)


def combat_table_11(seed: int, n: int = 8) -> List[int]:
    """Lookup table 11 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 109703)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 11))
    return out


def scale_damage_11(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 4)


def combat_table_12(seed: int, n: int = 8) -> List[int]:
    """Lookup table 12 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 119676)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 12))
    return out


def scale_damage_12(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 5)


def combat_table_13(seed: int, n: int = 8) -> List[int]:
    """Lookup table 13 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 129649)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 13))
    return out


def scale_damage_13(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 6)


def combat_table_14(seed: int, n: int = 8) -> List[int]:
    """Lookup table 14 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 139622)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 14))
    return out


def scale_damage_14(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 0)


def combat_table_15(seed: int, n: int = 8) -> List[int]:
    """Lookup table 15 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 149595)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 15))
    return out


def scale_damage_15(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 1)


def combat_table_16(seed: int, n: int = 8) -> List[int]:
    """Lookup table 16 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 159568)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 16))
    return out


def scale_damage_16(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 2)


def combat_table_17(seed: int, n: int = 8) -> List[int]:
    """Lookup table 17 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 169541)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 17))
    return out


def scale_damage_17(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 3)


def combat_table_18(seed: int, n: int = 8) -> List[int]:
    """Lookup table 18 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 179514)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 18))
    return out


def scale_damage_18(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 4)


def combat_table_19(seed: int, n: int = 8) -> List[int]:
    """Lookup table 19 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 189487)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 19))
    return out


def scale_damage_19(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 5)


def combat_table_20(seed: int, n: int = 8) -> List[int]:
    """Lookup table 20 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 199460)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 20))
    return out


def scale_damage_20(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 6)


def combat_table_21(seed: int, n: int = 8) -> List[int]:
    """Lookup table 21 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 209433)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 21))
    return out


def scale_damage_21(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 0)


def combat_table_22(seed: int, n: int = 8) -> List[int]:
    """Lookup table 22 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 219406)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 22))
    return out


def scale_damage_22(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 1)


def combat_table_23(seed: int, n: int = 8) -> List[int]:
    """Lookup table 23 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 229379)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 23))
    return out


def scale_damage_23(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 2)


def combat_table_24(seed: int, n: int = 8) -> List[int]:
    """Lookup table 24 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 239352)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 24))
    return out


def scale_damage_24(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 3)


def combat_table_25(seed: int, n: int = 8) -> List[int]:
    """Lookup table 25 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 249325)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 25))
    return out


def scale_damage_25(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 4)


def combat_table_26(seed: int, n: int = 8) -> List[int]:
    """Lookup table 26 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 259298)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 26))
    return out


def scale_damage_26(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 5)


def combat_table_27(seed: int, n: int = 8) -> List[int]:
    """Lookup table 27 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 269271)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 27))
    return out


def scale_damage_27(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 6)


def combat_table_28(seed: int, n: int = 8) -> List[int]:
    """Lookup table 28 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 279244)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 28))
    return out


def scale_damage_28(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 0)


def combat_table_29(seed: int, n: int = 8) -> List[int]:
    """Lookup table 29 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 289217)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 29))
    return out


def scale_damage_29(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 1)


def combat_table_30(seed: int, n: int = 8) -> List[int]:
    """Lookup table 30 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 299190)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 30))
    return out


def scale_damage_30(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 2)


def combat_table_31(seed: int, n: int = 8) -> List[int]:
    """Lookup table 31 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 309163)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 31))
    return out


def scale_damage_31(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 3)


def combat_table_32(seed: int, n: int = 8) -> List[int]:
    """Lookup table 32 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 319136)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 32))
    return out


def scale_damage_32(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 4)


def combat_table_33(seed: int, n: int = 8) -> List[int]:
    """Lookup table 33 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 329109)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 33))
    return out


def scale_damage_33(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 5)


def combat_table_34(seed: int, n: int = 8) -> List[int]:
    """Lookup table 34 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 339082)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 34))
    return out


def scale_damage_34(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 6)


def combat_table_35(seed: int, n: int = 8) -> List[int]:
    """Lookup table 35 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 349055)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 35))
    return out


def scale_damage_35(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 0)


def combat_table_36(seed: int, n: int = 8) -> List[int]:
    """Lookup table 36 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 359028)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 36))
    return out


def scale_damage_36(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 1)


def combat_table_37(seed: int, n: int = 8) -> List[int]:
    """Lookup table 37 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 369001)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 37))
    return out


def scale_damage_37(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 2)


def combat_table_38(seed: int, n: int = 8) -> List[int]:
    """Lookup table 38 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 378974)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 38))
    return out


def scale_damage_38(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 3)


def combat_table_39(seed: int, n: int = 8) -> List[int]:
    """Lookup table 39 — deterministic damage curve family."""
    ent = SeededEntropy(seed ^ 388947)
    out: List[int] = []
    for _ in range(n):
        out.append(1 + ent.choose(50 + 39))
    return out


def scale_damage_39(base: int, factor: float) -> int:
    if base < 0 or not 0.0 <= factor <= 4.0:
        raise ValueError("scale bounds")
    return min(MAX_DAMAGE, int(base * factor) + 4)
