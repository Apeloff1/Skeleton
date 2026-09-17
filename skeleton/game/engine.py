"""Deterministic mechanics execution. No wall clock. No uuid. No globals."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from skeleton.game.clock import GameClock, MAX_TICKS
from skeleton.game.mechanics import (
    CombatStyle,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsError,
    ProgressionStyle,
    ProgressionSystemSpec,
)


ALLOWED_VERBS = frozenset({"wait", "attack", "defend", "buy", "grant_xp"})
MAX_INPUTS = 2_048


class EngineError(GameMechanicsError):
    code = "GAME.ENGINE"


def _seed_int(seed: int | str) -> int:
    if isinstance(seed, bool) or not isinstance(seed, (int, str)):
        raise EngineError("seed must be int or str")
    if isinstance(seed, int):
        if seed < 0:
            raise EngineError("seed must be >= 0")
        return seed
    text = seed.strip()
    if not text:
        raise EngineError("seed must not be empty")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _draw(seed: int, tick: int, lane: str) -> int:
    material = f"{seed}:{tick}:{lane}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


@dataclass(frozen=True, slots=True)
class WorldState:
    tick: int
    hp: int
    heat: int
    gold: int
    xp: int
    level: int
    defending: bool

    def snapshot(self) -> dict[str, int | bool]:
        return {
            "tick": self.tick,
            "hp": self.hp,
            "heat": self.heat,
            "gold": self.gold,
            "xp": self.xp,
            "level": self.level,
            "defending": self.defending,
        }


def _xp_needed(spec: ProgressionSystemSpec, level: int) -> int:
    base = 100
    if spec.style == ProgressionStyle.EXPONENTIAL:
        return int(base * (1.5 ** level))
    if spec.style == ProgressionStyle.LOGARITHMIC:
        return int(base * (level + 8))
    return base * max(level, 1)


class DeterministicEngine:
    """Tick combat / economy / progression with an explicit seed and clock."""

    def __init__(
        self,
        *,
        seed: int | str,
        combat: CombatSystemSpec | None = None,
        economy: EconomySystemSpec | None = None,
        progression: ProgressionSystemSpec | None = None,
        hz: int = 60,
    ) -> None:
        self.seed = _seed_int(seed)
        self.combat = combat or CombatSystemSpec(style=CombatStyle.TURN_BASED)
        self.economy = economy or EconomySystemSpec()
        self.progression = progression or ProgressionSystemSpec(style=ProgressionStyle.LINEAR)
        self.clock = GameClock(tick=0, hz=hz)
        roll = _draw(self.seed, 0, "init")
        self.state = WorldState(
            tick=0,
            hp=40 + (roll % 21),
            heat=0,
            gold=10 + ((roll >> 8) % 21),
            xp=0,
            level=1,
            defending=False,
        )

    def spec_card(self) -> dict[str, Any]:
        return {
            "combat_style": self.combat.style.value,
            "include_magic": self.combat.include_magic,
            "currencies": list(self.economy.currencies),
            "progression_style": self.progression.style.value,
            "max_level": self.progression.max_level,
            "hz": self.clock.hz,
            "seed": self.seed,
        }

    def apply(self, verb: str) -> WorldState:
        verb = str(verb or "").strip().lower()
        if verb not in ALLOWED_VERBS:
            raise EngineError(f"unknown verb: {verb or '<empty>'}")
        tick = self.clock.tick
        hp = self.state.hp
        heat = max(0, self.state.heat - 1)
        gold = self.state.gold
        xp = self.state.xp
        level = self.state.level
        defending = False
        if verb == "attack":
            roll = _draw(self.seed, tick, "atk")
            dmg = 4 + (roll % 5)
            if self.combat.include_magic:
                dmg += 1
            hp = max(0, hp - dmg)
            heat = min(100, heat + 6)
            xp += 3
        elif verb == "defend":
            defending = True
            heat = max(0, heat - 4)
            hp = min(80, hp + 1)
        elif verb == "buy":
            price = 5
            if gold < price:
                raise EngineError("insufficient gold")
            gold -= price
            hp = min(80, hp + 8)
        elif verb == "grant_xp":
            xp += 25
        needed = _xp_needed(self.progression, level)
        while xp >= needed and level < self.progression.max_level:
            xp -= needed
            level += 1
            hp = min(80, hp + 6)
            needed = _xp_needed(self.progression, level)
        self.clock = self.clock.advance(1)
        self.state = WorldState(
            tick=self.clock.tick,
            hp=hp,
            heat=heat,
            gold=gold,
            xp=xp,
            level=level,
            defending=defending,
        )
        return self.state

    def run(self, inputs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = [self.state.snapshot()]
        pending = list(inputs)
        if len(pending) > MAX_INPUTS:
            raise EngineError("too many inputs")
        by_tick: dict[int, str] = {}
        for raw in pending:
            if not isinstance(raw, Mapping):
                raise EngineError("input must be an object")
            if "t" not in raw or "verb" not in raw:
                raise EngineError("input requires t and verb")
            t = raw["t"]
            if isinstance(t, bool) or not isinstance(t, int) or t < 0 or t > MAX_TICKS:
                raise EngineError("input t is out of range")
            if t in by_tick:
                raise EngineError("duplicate input tick")
            by_tick[t] = str(raw["verb"])
        last = max(by_tick) if by_tick else 0
        if last >= MAX_TICKS:
            raise EngineError("input t exceeds tick ceiling")
        while self.clock.tick <= last:
            verb = by_tick.get(self.clock.tick, "wait")
            self.apply(verb)
            frames.append(self.state.snapshot())
        return frames
