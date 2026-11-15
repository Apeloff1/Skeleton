"""Bounded integer-tick clock and tamper-evident input replay for game simulation.

No wall clock or floating-point accumulation enters the deterministic state.
This module does not claim engine, renderer or device qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping

SCHEMA = "skeleton.game.fixed-tick.v1"
MAX_TICKS = 10_000_000
MAX_EVENTS = 100_000
MAX_ACTION_BYTES = 256
_ACTIONS = frozenset({"up", "down", "left", "right", "interact", "attack", "pause", "resume"})


class ReplayError(ValueError):
    """Invalid, out-of-order, or divergent game input history."""


def _integer(value: object, label: str, upper: int) -> int:
    if type(value) is not int or not 0 <= value <= upper:
        raise ReplayError(f"{label} must be an integer in [0, {upper}]")
    return value


def _digest(record: Mapping[str, object]) -> str:
    return sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class InputEvent:
    tick: int
    action: str
    pressed: bool

    def __post_init__(self) -> None:
        _integer(self.tick, "tick", MAX_TICKS)
        if type(self.action) is not str or self.action not in _ACTIONS:
            raise ReplayError("action is not on the canonical input allowlist")
        if len(self.action.encode("utf-8")) > MAX_ACTION_BYTES:
            raise ReplayError("action exceeds byte budget")
        if type(self.pressed) is not bool:
            raise ReplayError("pressed must be boolean")


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    tick: int
    events: tuple[InputEvent, ...]
    prior_digest: str
    digest: str


class FixedTickReplay:
    """Deterministic append-only action log with explicit restart verification."""

    def __init__(self, *, hz: int = 60, seed: int = 0) -> None:
        _integer(hz, "hz", 240)
        if hz == 0:
            raise ReplayError("hz must be positive")
        _integer(seed, "seed", 2**63 - 1)
        self.hz = hz
        self.seed = seed
        self.tick = 0
        self._frames: list[ReplayFrame] = []
        self._head = _digest({"schema": SCHEMA, "hz": hz, "seed": seed})

    @property
    def digest(self) -> str:
        return self._head

    @property
    def frames(self) -> tuple[ReplayFrame, ...]:
        return tuple(self._frames)

    def advance(self, events: tuple[InputEvent, ...] = ()) -> ReplayFrame:
        if self.tick >= MAX_TICKS or len(self._frames) >= MAX_EVENTS:
            raise ReplayError("replay budget exhausted")
        if type(events) is not tuple or len(events) > 32:
            raise ReplayError("events must be a bounded tuple")
        next_tick = self.tick + 1
        canonical_events = []
        for event in events:
            if type(event) is not InputEvent:
                raise ReplayError("event must be canonical InputEvent")
            # Frozen dataclasses alone do not prove integrity: callers can
            # construct or mutate slots using object.__setattr__.
            captured = InputEvent(event.tick, event.action, event.pressed)
            if captured.tick != next_tick:
                raise ReplayError("event tick must match next simulation tick")
            canonical_events.append(captured)
        events = tuple(canonical_events)
        payload = {"schema": SCHEMA, "tick": next_tick, "prior": self._head,
                   "events": [{"action": e.action, "pressed": e.pressed} for e in events]}
        head = _digest(payload)
        frame = ReplayFrame(next_tick, events, self._head, head)
        self._frames.append(frame)
        self._head = head
        self.tick = next_tick
        return frame

    @classmethod
    def verify(cls, *, hz: int, seed: int, frames: tuple[ReplayFrame, ...]) -> "FixedTickReplay":
        if type(frames) is not tuple or len(frames) > MAX_EVENTS:
            raise ReplayError("invalid replay frame collection")
        replay = cls(hz=hz, seed=seed)
        for frame in frames:
            if type(frame) is not ReplayFrame:
                raise ReplayError("invalid replay frame")
            _integer(frame.tick, "frame tick", MAX_TICKS)
            if any(type(value) is not str or len(value) != 64
                   or any(char not in "0123456789abcdef" for char in value)
                   for value in (frame.prior_digest, frame.digest)):
                raise ReplayError("invalid replay frame digest")
            expected = replay.advance(frame.events)
            if (expected.tick != frame.tick or expected.prior_digest != frame.prior_digest
                    or expected.digest != frame.digest):
                raise ReplayError("replay divergence or tampering")
        return replay
