"""Bounded integer-time fixed-step simulation clock for canonical game playback.

The clock never reads wall time. Hosts supply elapsed microseconds explicitly; the
same elapsed sequence yields identical tick receipts after process restart.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

CLOCK_SCHEMA = "skeleton.game.fixed_clock.v1"
MAX_ELAPSED_US = 10_000_000
MAX_TICKS_PER_ADVANCE = 8
MAX_TICK = 2**53 - 1


class ClockBoundaryError(ValueError):
    """Invalid clock authority or bounded simulation request."""


def _integer(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ClockBoundaryError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


@dataclass(frozen=True, slots=True)
class ClockState:
    tick: int = 0
    remainder_us: int = 0
    dropped_us: int = 0
    step_us: int = 16_667

    def __post_init__(self) -> None:
        _integer("tick", self.tick, 0, MAX_TICK)
        _integer("step_us", self.step_us, 1_000, 1_000_000)
        _integer("remainder_us", self.remainder_us, 0, self.step_us - 1)
        _integer("dropped_us", self.dropped_us, 0, MAX_TICK)

    def to_record(self) -> dict[str, int | str]:
        return {
            "schema": CLOCK_SCHEMA,
            "tick": self.tick,
            "remainder_us": self.remainder_us,
            "dropped_us": self.dropped_us,
            "step_us": self.step_us,
        }

    @classmethod
    def from_record(cls, record: object) -> "ClockState":
        if not isinstance(record, dict) or set(record) != {
            "schema", "tick", "remainder_us", "dropped_us", "step_us"
        } or record["schema"] != CLOCK_SCHEMA:
            raise ClockBoundaryError("invalid or incompatible clock checkpoint")
        return cls(
            tick=record["tick"],
            remainder_us=record["remainder_us"],
            dropped_us=record["dropped_us"],
            step_us=record["step_us"],
        )

    def digest(self) -> str:
        payload = json.dumps(self.to_record(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ClockAdvance:
    before: ClockState
    after: ClockState
    ticks: tuple[int, ...]
    dropped_this_advance_us: int

    @property
    def replay_digest(self) -> str:
        payload = {
            "before": self.before.digest(),
            "after": self.after.digest(),
            "ticks": self.ticks,
            "dropped": self.dropped_this_advance_us,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def advance_clock(
    state: ClockState, elapsed_us: int, *, max_steps: int = MAX_TICKS_PER_ADVANCE
) -> ClockAdvance:
    """Advance bounded ticks, dropping excess elapsed time rather than spiralling.

    The host must record elapsed_us for replay. The simulation never invents
    additional ticks after overload; dropped time is explicit and checkpointed.
    """
    if not isinstance(state, ClockState):
        raise ClockBoundaryError("clock state required")
    _integer("elapsed_us", elapsed_us, 0, MAX_ELAPSED_US)
    _integer("max_steps", max_steps, 1, MAX_TICKS_PER_ADVANCE)
    accumulated = state.remainder_us + elapsed_us
    available, remainder = divmod(accumulated, state.step_us)
    emitted = min(available, max_steps)
    dropped = (available - emitted) * state.step_us
    if state.tick + emitted > MAX_TICK or state.dropped_us + dropped > MAX_TICK:
        raise ClockBoundaryError("clock counter exhausted")
    after = ClockState(
        tick=state.tick + emitted,
        remainder_us=remainder,
        dropped_us=state.dropped_us + dropped,
        step_us=state.step_us,
    )
    return ClockAdvance(
        before=state,
        after=after,
        ticks=tuple(range(state.tick + 1, after.tick + 1)),
        dropped_this_advance_us=dropped,
    )
