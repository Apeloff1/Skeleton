"""Deterministic combat engine for B021.

Frame-based strikes with seeded entropy. Same seed+tick → same StrikeResult.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.simulation.game.mechanics_depth.tick_clock import SeededEntropy, TickClock

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
