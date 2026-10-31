"""B048 schedules and systemic world time: deterministic, save-compatible."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class WorldTimeError(ValueError):
    pass


@dataclass(frozen=True)
class WorldClock:
    tick: int = 0
    ticks_per_hour: int = 60
    hours_per_day: int = 24

    def advance(self, n: int) -> "WorldClock":
        if n < 0:
            raise WorldTimeError("time cannot go backwards")
        return WorldClock(self.tick + n, self.ticks_per_hour, self.hours_per_day)

    @property
    def day(self) -> int:
        return self.tick // (self.ticks_per_hour * self.hours_per_day)

    @property
    def hour(self) -> int:
        return (self.tick // self.ticks_per_hour) % self.hours_per_day

    def to_dict(self) -> dict[str, int]:
        return {"tick": self.tick, "ticks_per_hour": self.ticks_per_hour, "hours_per_day": self.hours_per_day}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "WorldClock":
        return cls(int(d["tick"]), int(d.get("ticks_per_hour", 60)), int(d.get("hours_per_day", 24)))


@dataclass(frozen=True)
class ScheduleEntry:
    start_hour: int
    activity: str
    location: str

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour < 24:
            raise WorldTimeError("start_hour out of range")


def activity_at(schedule: Sequence[ScheduleEntry], hour: int) -> ScheduleEntry:
    if not schedule:
        raise WorldTimeError("empty schedule")
    ordered = sorted(schedule, key=lambda e: (e.start_hour, e.activity))
    current = ordered[-1]  # wraps from previous day
    for e in ordered:
        if e.start_hour <= hour:
            current = e
    return current


def resolve_world(clock: WorldClock, schedules: Mapping[str, Sequence[ScheduleEntry]]) -> dict[str, dict[str, str]]:
    return {npc: {"activity": (e := activity_at(s, clock.hour)).activity, "location": e.location}
            for npc, s in sorted(schedules.items())}


def transitions(prev: WorldClock, nxt: WorldClock,
                schedules: Mapping[str, Sequence[ScheduleEntry]]) -> list[dict[str, Any]]:
    """Events emitted when an NPC's activity changes between two clock states."""
    a, b = resolve_world(prev, schedules), resolve_world(nxt, schedules)
    return [{"tick": nxt.tick, "npc": k, "from": a[k], "to": b[k]} for k in sorted(b) if a.get(k) != b[k]]
