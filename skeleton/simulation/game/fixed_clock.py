"""Bounded deterministic fixed-step game clock with restart custody.

The caller owns real-time measurement and must submit integer microseconds.
No wall clock, randomness, provider, filesystem, or global mutable state is read.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

SCHEMA = "game.fixed_clock.v1"
MAX_TICK = 1_000_000_000
MAX_DELTA_US = 1_000_000
MAX_ACCUMULATED_US = 2_000_000
MAX_STEPS_PER_FRAME = 8


class FixedClockError(ValueError):
    """Invalid, stale or corrupted simulation clock transition."""


def _integer(name: str, value: object, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise FixedClockError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def _digest(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FixedClock:
    tick_us: int = 16_667
    tick: int = 0
    remainder_us: int = 0

    def __post_init__(self) -> None:
        _integer("tick_us", self.tick_us, 1_000, 100_000)
        _integer("tick", self.tick, 0, MAX_TICK)
        _integer("remainder_us", self.remainder_us, 0, MAX_ACCUMULATED_US)
        if self.remainder_us >= self.tick_us:
            raise FixedClockError("remainder must be smaller than tick duration")

    def advance(self, elapsed_us: int) -> tuple["FixedClock", int]:
        _integer("elapsed_us", elapsed_us, 0, MAX_DELTA_US)
        total = self.remainder_us + elapsed_us
        steps = total // self.tick_us
        if steps > MAX_STEPS_PER_FRAME:
            raise FixedClockError("frame exceeds bounded simulation step budget")
        if self.tick + steps > MAX_TICK:
            raise FixedClockError("simulation tick overflow")
        return FixedClock(self.tick_us, self.tick + steps, total % self.tick_us), steps

    def snapshot(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": SCHEMA, "tick_us": self.tick_us,
            "tick": self.tick, "remainder_us": self.remainder_us,
        }
        return {**payload, "sha256": _digest(payload)}

    @classmethod
    def restore(cls, raw: Mapping[str, object]) -> "FixedClock":
        if not isinstance(raw, Mapping):
            raise FixedClockError("snapshot must be an object")
        required = {"schema", "tick_us", "tick", "remainder_us", "sha256"}
        if set(raw) != required or raw["schema"] != SCHEMA:
            raise FixedClockError("snapshot schema or fields invalid")
        payload = {key: raw[key] for key in required - {"sha256"}}
        clock = cls(
            tick_us=_integer("tick_us", raw["tick_us"], 1_000, 100_000),
            tick=_integer("tick", raw["tick"], 0, MAX_TICK),
            remainder_us=_integer("remainder_us", raw["remainder_us"], 0, MAX_ACCUMULATED_US),
        )
        if type(raw["sha256"]) is not str or _digest(payload) != raw["sha256"]:
            raise FixedClockError("snapshot integrity mismatch")
        return clock
