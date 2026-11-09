"""Sessions, funnels, retention, per-level/encounter drop-off and difficulty heatmap."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .events import EventType as T
from .events import GameplayEvent
from .privacy import ANON

HEATMAP_SCHEMA = "skeleton.game_builder.analytics.difficulty_heatmap.v1"


def _ordered(events: Iterable[GameplayEvent]) -> list[GameplayEvent]:
    return sorted(events, key=lambda e: (e.player, e.day, e.session_id, e.seq))


@dataclass(frozen=True)
class Session:
    session_id: str
    player: str
    day: int
    duration: float
    events: tuple[GameplayEvent, ...]
    ended: str  # "session_end" | "quit" | "truncated"

    @property
    def levels_completed(self) -> tuple[str, ...]:
        return tuple(e.level_id for e in self.events if e.type is T.LEVEL_COMPLETE)


def build_sessions(events: Iterable[GameplayEvent]) -> list[Session]:
    by: dict[str, list[GameplayEvent]] = defaultdict(list)
    for e in events:
        by[e.session_id].append(e)
    out = []
    for sid, evs in by.items():
        evs.sort(key=lambda e: e.seq)
        last = evs[-1].type
        ended = "session_end" if last is T.SESSION_END else "quit" if last is T.QUIT else "truncated"
        out.append(Session(sid, evs[0].player, min(e.day for e in evs), max(e.t for e in evs) - evs[0].t,
                           tuple(evs), ended))
    return sorted(out, key=lambda s: (s.player, s.day, s.events[0].seq, s.session_id))


@dataclass(frozen=True)
class FunnelResult:
    steps: tuple[str, ...]
    reached: tuple[int, ...]

    @property
    def conversion(self) -> tuple[float, ...]:
        top = self.reached[0] if self.reached else 0
        return tuple(round(r / top, 4) if top else 0.0 for r in self.reached)

    def to_dict(self) -> dict[str, Any]:
        return {"steps": list(self.steps), "reached": list(self.reached), "conversion": list(self.conversion)}


@dataclass(frozen=True)
class Funnel:
    """Ordered steps, each ``"<event_type>"`` or ``"<event_type>:<level_id>[:<encounter_id>]"``.

    Counted per player (per session for anonymised events, which are unlinkable),
    steps must happen in order.
    """

    steps: tuple[str, ...]

    @staticmethod
    def _match(step: str, e: GameplayEvent) -> bool:
        parts = step.split(":")
        if e.type.value != parts[0]:
            return False
        if len(parts) > 1 and e.level_id != parts[1]:
            return False
        return len(parts) < 3 or e.encounter_id == parts[2]

    def run(self, events: Iterable[GameplayEvent]) -> FunnelResult:
        reached = [0] * len(self.steps)
        units: dict[str, list[GameplayEvent]] = defaultdict(list)
        for e in _ordered(events):
            units[e.session_id if e.player == ANON else e.player].append(e)
        for evs in units.values():
            i = 0
            for e in evs:
                if i < len(self.steps) and self._match(self.steps[i], e):
                    reached[i] += 1
                    i += 1
        return FunnelResult(tuple(self.steps), tuple(reached))


def retention(sessions: Sequence[Session], days: Sequence[int] = (1, 7, 30)) -> dict[str, Any]:
    """Classic day-N retention by first-seen-day cohort. Anonymised sessions are excluded."""
    seen: dict[str, set[int]] = defaultdict(set)
    for s in sessions:
        if s.player != ANON:
            seen[s.player].add(s.day)
    cohort = len(seen)
    res = {f"d{n}": round(sum(1 for d in seen.values() if min(d) + n in d) / cohort, 4) if cohort else 0.0
           for n in days}
    return {"players": cohort, **res}


@dataclass
class StageStats:
    level_id: str
    encounter_id: str | None
    attempts: int = 0
    completions: int = 0
    failures: int = 0
    deaths: int = 0
    drop_offs: int = 0  # units whose last attempt here was never completed and who then stopped
    units: set[str] = field(default_factory=set)
    clear_times: list[float] = field(default_factory=list)

    @property
    def fail_rate(self) -> float:
        done = self.completions + self.failures
        return round(self.failures / done, 4) if done else 0.0

    @property
    def drop_off_rate(self) -> float:
        return round(self.drop_offs / len(self.units), 4) if self.units else 0.0


def stage_stats(events: Iterable[GameplayEvent]) -> dict[tuple[str, str | None], StageStats]:
    """Per level (encounter_id None) and per (level, encounter) stats including drop-off."""
    stats: dict[tuple[str, str | None], StageStats] = {}

    def get(lv: str, enc: str | None) -> StageStats:
        return stats.setdefault((lv, enc), StageStats(lv, enc))

    units: dict[str, list[GameplayEvent]] = defaultdict(list)
    for e in _ordered(events):
        units[e.session_id if e.player == ANON else e.player].append(e)
    for unit, evs in units.items():
        open_at: dict[tuple[str, str | None], float] = {}
        for e in evs:
            if e.level_id is None:
                continue
            key = (e.level_id, e.encounter_id if e.type in (T.ENCOUNTER_START, T.ENCOUNTER_COMPLETE,
                                                            T.ENCOUNTER_FAIL) else None)
            if e.type in (T.LEVEL_START, T.ENCOUNTER_START):
                st = get(*key)
                st.attempts += 1
                st.units.add(unit)
                open_at[key] = e.t
            elif e.type in (T.LEVEL_COMPLETE, T.ENCOUNTER_COMPLETE):
                st = get(*key)
                st.completions += 1
                st.units.add(unit)
                if key in open_at:
                    st.clear_times.append(max(0.0, e.t - open_at.pop(key)))
            elif e.type in (T.LEVEL_FAIL, T.ENCOUNTER_FAIL):
                st = get(*key)
                st.failures += 1
                st.units.add(unit)
                open_at.pop(key, None)
            elif e.type is T.DEATH:
                get(e.level_id, None).deaths += 1
                if e.encounter_id is not None:
                    get(e.level_id, e.encounter_id).deaths += 1
        # Drop-off: the unit's final level (and encounter) touched was never cleared after its last start.
        for key in _uncleared_tail(evs):
            stats[key].drop_offs += 1
    return stats


def _uncleared_tail(evs: list[GameplayEvent]) -> list[tuple[str, str | None]]:
    last_lv = next((e for e in reversed(evs) if e.level_id is not None and e.type in
                    (T.LEVEL_START, T.LEVEL_COMPLETE, T.LEVEL_FAIL, T.ENCOUNTER_START, T.ENCOUNTER_COMPLETE,
                     T.ENCOUNTER_FAIL)), None)
    if last_lv is None:
        return []
    lv = last_lv.level_id
    out: list[tuple[str, str | None]] = []
    lv_evs = [e for e in evs if e.level_id == lv]
    if not any(e.type is T.LEVEL_COMPLETE for e in lv_evs[_last_index(lv_evs, T.LEVEL_START):]) \
            and any(e.type is T.LEVEL_START for e in lv_evs):
        out.append((lv, None))
        enc = next((e for e in reversed(lv_evs) if e.encounter_id is not None and e.type in
                    (T.ENCOUNTER_START, T.ENCOUNTER_COMPLETE, T.ENCOUNTER_FAIL)), None)
        if enc is not None and enc.type is not T.ENCOUNTER_COMPLETE:
            out.append((lv, enc.encounter_id))
    return out


def _last_index(evs: list[GameplayEvent], typ: T) -> int:
    for i in range(len(evs) - 1, -1, -1):
        if evs[i].type is typ:
            return i
    return 0


@dataclass(frozen=True)
class DifficultyCell:
    level_id: str
    encounter_id: str | None
    players: int
    attempts: int
    completions: int
    failures: int
    deaths: int
    drop_offs: int
    fail_rate: float
    drop_off_rate: float
    attempts_per_clear: float | None
    median_clear_s: float | None
    difficulty: float  # 0..1: 0.6*fail_rate + 0.4*drop_off_rate
    low_confidence: bool


@dataclass(frozen=True)
class DifficultyHeatmap:
    """Plain-data difficulty map keyed by the plan's level and encounter ids."""

    cells: tuple[DifficultyCell, ...]
    min_players: int
    suppressed: int = 0  # cells hidden for having fewer than ``min_players`` units
    schema: str = HEATMAP_SCHEMA

    def __post_init__(self) -> None:
        # Never deserialize or publish a heatmap with a disabled privacy
        # threshold or with nonempty cells smaller than its stated cohort.
        if type(self.min_players) is not int or not 1 <= self.min_players <= 1_000_000:
            raise ValueError("min_players must be a positive bounded integer")
        if type(self.suppressed) is not int or self.suppressed < 0:
            raise ValueError("suppressed must be a non-negative integer")
        for cell in self.cells:
            if (type(cell.players) is not int or cell.players < 0
                    or 0 < cell.players < self.min_players):
                raise ValueError("heatmap cell violates minimum player threshold")

    def cell(self, level_id: str, encounter_id: str | None = None) -> DifficultyCell | None:
        return next((c for c in self.cells if (c.level_id, c.encounter_id) == (level_id, encounter_id)), None)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "min_players": self.min_players, "suppressed": self.suppressed,
                "cells": [asdict(c) for c in self.cells]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DifficultyHeatmap:
        if d.get("schema") != HEATMAP_SCHEMA:
            raise ValueError("unsupported heatmap schema")
        return cls(tuple(DifficultyCell(**c) for c in d["cells"]), d["min_players"], d.get("suppressed", 0))


def plan_ids(plan: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """(level_id, None) and (level_id, encounter_id) keys from a plan's ``levels[].encounters[]``."""
    keys: list[tuple[str, str | None]] = []
    for lv in plan.get("levels") or []:
        lid = (lv.get("id") or lv.get("level_id")) if isinstance(lv, Mapping) else None
        if not isinstance(lid, str):
            continue
        keys.append((lid, None))
        for enc in lv.get("encounters") or []:
            eid = (enc.get("id") or enc.get("encounter_id")) if isinstance(enc, Mapping) else enc
            if isinstance(eid, str):
                keys.append((lid, eid))
    return keys


def difficulty_heatmap(events: Iterable[GameplayEvent], plan: Mapping[str, Any] | None = None,
                       *, min_players: int = 5) -> DifficultyHeatmap:
    """Build the heatmap. With ``plan`` the cells follow plan order, include unplayed ids
    (zeros, low_confidence) and ignore ids the plan does not know."""
    stats = stage_stats(events)
    keys = plan_ids(plan) if plan is not None else sorted(stats, key=lambda k: (k[0], k[1] or ""))
    cells, suppressed = [], 0
    for key in keys:
        st = stats.get(key) or StageStats(*key)
        n = len(st.units)
        if 0 < n < min_players:
            suppressed += 1
            continue
        cells.append(DifficultyCell(
            level_id=key[0], encounter_id=key[1], players=n, attempts=st.attempts, completions=st.completions,
            failures=st.failures, deaths=st.deaths, drop_offs=st.drop_offs, fail_rate=st.fail_rate,
            drop_off_rate=st.drop_off_rate,
            attempts_per_clear=round(st.attempts / st.completions, 3) if st.completions else None,
            median_clear_s=round(median(st.clear_times), 3) if st.clear_times else None,
            difficulty=round(0.6 * st.fail_rate + 0.4 * st.drop_off_rate, 4), low_confidence=n < min_players))
    return DifficultyHeatmap(tuple(cells), min_players, suppressed)
