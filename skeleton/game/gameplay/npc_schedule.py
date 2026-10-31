"""Offline, deterministic NPC schedules and player interactions for FLGB gameplay.

All commands are source-bound, immutable and replayable. This module owns no network
service and consumes the canonical FLGB-13 EventBus and SaveableGameplayState.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .flgb_gameplay_runtime import (
    EventBus, GameplayContractError, SaveableGameplayState, dig, req_digest, req_id,
)

MAX_NPCS = 512
MAX_STOPS = 256
MAX_FACTS = 4096
MAX_COMMANDS = 8192
MAX_HORIZON = 1_000_000


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GameplayContractError(f"invalid {name}")
    return value


def _keys(value: Any, expected: set[str], name: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise GameplayContractError(f"invalid {name} fields")
    return value


def _facts(value: Any, name: str) -> tuple[str, ...]:
    if type(value) is not list or len(value) > MAX_FACTS:
        raise GameplayContractError(f"invalid {name}")
    facts = tuple(req_id(item, name) for item in value)
    if len(set(facts)) != len(facts):
        raise GameplayContractError(f"duplicate {name}")
    return tuple(sorted(facts))


@dataclass(frozen=True)
class NpcStop:
    start_tick: int
    end_tick: int
    location_id: str
    interaction_id: str
    requires: tuple[str, ...]
    grants: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Any, horizon: int) -> "NpcStop":
        row = _keys(raw, {"start_tick", "end_tick", "location_id",
                          "interaction_id", "requires", "grants"}, "stop")
        start = _integer(row["start_tick"], "start_tick", 0, horizon)
        end = _integer(row["end_tick"], "end_tick", 1, horizon + 1)
        if end <= start:
            raise GameplayContractError("empty NPC stop")
        return cls(start, end, req_id(row["location_id"], "location_id"),
                   req_id(row["interaction_id"], "interaction_id"),
                   _facts(row["requires"], "requires"),
                   _facts(row["grants"], "grants"))

    def as_dict(self) -> dict[str, Any]:
        return {"start_tick": self.start_tick, "end_tick": self.end_tick,
                "location_id": self.location_id, "interaction_id": self.interaction_id,
                "requires": list(self.requires), "grants": list(self.grants)}


@dataclass(frozen=True)
class NpcRoute:
    npc_id: str
    stops: tuple[NpcStop, ...]

    @classmethod
    def parse(cls, raw: Any, horizon: int) -> "NpcRoute":
        row = _keys(raw, {"npc_id", "stops"}, "route")
        stops_raw = row["stops"]
        if type(stops_raw) is not list or not 1 <= len(stops_raw) <= MAX_STOPS:
            raise GameplayContractError("invalid NPC stop count")
        stops = tuple(sorted((NpcStop.parse(s, horizon) for s in stops_raw),
                             key=lambda s: (s.start_tick, s.end_tick)))
        if any(a.end_tick > b.start_tick for a, b in zip(stops, stops[1:])):
            raise GameplayContractError("overlapping NPC stops")
        if len({s.interaction_id for s in stops}) != len(stops):
            raise GameplayContractError("duplicate NPC interaction")
        return cls(req_id(row["npc_id"], "npc_id"), stops)

    def at(self, tick: int) -> NpcStop | None:
        for stop in self.stops:
            if stop.start_tick <= tick < stop.end_tick:
                return stop
        return None

    def as_dict(self) -> dict[str, Any]:
        return {"npc_id": self.npc_id, "stops": [s.as_dict() for s in self.stops]}


@dataclass(frozen=True)
class NpcSchedule:
    world_id: str
    canon_digest: str
    horizon_ticks: int
    initial_facts: tuple[str, ...]
    routes: tuple[NpcRoute, ...]

    @classmethod
    def parse(cls, raw: Any) -> "NpcSchedule":
        row = _keys(raw, {"schema_version", "world_id", "canon_digest",
                          "horizon_ticks", "initial_facts", "routes"}, "schedule")
        if row["schema_version"] != 1 or type(row["schema_version"]) is not int:
            raise GameplayContractError("unsupported schedule schema")
        horizon = _integer(row["horizon_ticks"], "horizon_ticks", 1, MAX_HORIZON)
        routes_raw = row["routes"]
        if type(routes_raw) is not list or not 1 <= len(routes_raw) <= MAX_NPCS:
            raise GameplayContractError("invalid NPC route count")
        routes = tuple(sorted((NpcRoute.parse(r, horizon) for r in routes_raw),
                              key=lambda r: r.npc_id))
        if len({r.npc_id for r in routes}) != len(routes):
            raise GameplayContractError("duplicate NPC route")
        return cls(req_id(row["world_id"], "world_id"),
                   req_digest(row["canon_digest"], "canon_digest"), horizon,
                   _facts(row["initial_facts"], "initial_facts"), routes)

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "world_id": self.world_id,
                "canon_digest": self.canon_digest, "horizon_ticks": self.horizon_ticks,
                "initial_facts": list(self.initial_facts),
                "routes": [r.as_dict() for r in self.routes]}

    @property
    def digest(self) -> str:
        return dig(self.as_dict())

    def active(self, tick: int) -> tuple[dict[str, str], ...]:
        _integer(tick, "tick", 0, self.horizon_ticks)
        return tuple({"npc_id": route.npc_id, "location_id": stop.location_id,
                      "interaction_id": stop.interaction_id}
                     for route in self.routes if (stop := route.at(tick)) is not None)


@dataclass(frozen=True)
class NpcCommand:
    kind: str
    tick: int
    npc_id: str | None = None
    interaction_id: str | None = None
    player_id: str | None = None

    @classmethod
    def parse(cls, raw: Any) -> "NpcCommand":
        if type(raw) is not dict or raw.get("kind") not in ("advance", "interact"):
            raise GameplayContractError("invalid NPC command")
        if raw["kind"] == "advance":
            row = _keys(raw, {"kind", "tick"}, "advance")
            return cls("advance", _integer(row["tick"], "tick", 0, MAX_HORIZON))
        row = _keys(raw, {"kind", "tick", "npc_id", "interaction_id",
                          "player_id"}, "interaction")
        return cls("interact", _integer(row["tick"], "tick", 0, MAX_HORIZON),
                   req_id(row["npc_id"], "npc_id"),
                   req_id(row["interaction_id"], "interaction_id"),
                   req_id(row["player_id"], "player_id"))

    def as_dict(self) -> dict[str, Any]:
        if self.kind == "advance":
            return {"kind": self.kind, "tick": self.tick}
        return {"kind": self.kind, "tick": self.tick, "npc_id": self.npc_id,
                "interaction_id": self.interaction_id, "player_id": self.player_id}


@dataclass(frozen=True)
class NpcSession:
    schedule: NpcSchedule
    tick: int
    facts: tuple[str, ...]
    commands: tuple[NpcCommand, ...]
    events: EventBus

    @classmethod
    def start(cls, schedule: NpcSchedule) -> "NpcSession":
        return cls(schedule, 0, schedule.initial_facts, (), EventBus())

    def apply(self, command: NpcCommand) -> "NpcSession":
        if len(self.commands) >= MAX_COMMANDS:
            raise GameplayContractError("NPC command budget exceeded")
        if command.kind == "advance":
            if not self.tick < command.tick <= self.schedule.horizon_ticks:
                raise GameplayContractError("non-monotonic schedule advance")
            payload = {"from": self.tick, "to": command.tick,
                       "active": list(self.schedule.active(command.tick))}
            bus = self.events.publish("npc.schedule.advance", self.schedule.world_id,
                                      dig(payload))
            return NpcSession(self.schedule, command.tick, self.facts,
                              self.commands + (command,), bus)
        if command.kind != "interact" or command.tick != self.tick:
            raise GameplayContractError("interaction tick mismatch")
        route = next((r for r in self.schedule.routes if r.npc_id == command.npc_id), None)
        stop = route.at(self.tick) if route else None
        if stop is None or stop.interaction_id != command.interaction_id:
            raise GameplayContractError("NPC interaction unavailable")
        if not set(stop.requires).issubset(self.facts):
            raise GameplayContractError("NPC interaction prerequisites missing")
        if any(c.kind == "interact" and c.npc_id == command.npc_id
               and c.interaction_id == command.interaction_id for c in self.commands):
            raise GameplayContractError("NPC interaction already consumed")
        facts = tuple(sorted(set(self.facts).union(stop.grants)))
        if len(facts) > MAX_FACTS:
            raise GameplayContractError("NPC fact budget exceeded")
        bus = self.events.publish("npc.schedule.interact", command.npc_id or "",
                                  dig({"tick": self.tick, "npc": command.npc_id,
                                       "player": command.player_id,
                                       "interaction": command.interaction_id,
                                       "location": stop.location_id,
                                       "granted": list(stop.grants)}))
        return NpcSession(self.schedule, self.tick, facts,
                          self.commands + (command,), bus)

    @property
    def state_digest(self) -> str:
        return dig({"world_id": self.schedule.world_id,
                    "schedule_digest": self.schedule.digest, "tick": self.tick,
                    "facts": list(self.facts), "events_digest": self.events.digest,
                    "commands": [c.as_dict() for c in self.commands]})

    def snapshot(self, parent_save_digest: str | None = None) -> dict[str, Any]:
        save = SaveableGameplayState(self.schedule.world_id, 1, self.tick,
                                    self.state_digest, self.schedule.canon_digest,
                                    parent_save_digest)
        return {"schema_version": 1, "schedule_digest": self.schedule.digest,
                "commands": [c.as_dict() for c in self.commands],
                "state_digest": self.state_digest, "save": dict(save.__dict__),
                "save_digest": save.digest}

    @classmethod
    def restore(cls, schedule: NpcSchedule, raw: Any) -> "NpcSession":
        row = _keys(raw, {"schema_version", "schedule_digest", "commands",
                          "state_digest", "save", "save_digest"}, "snapshot")
        if type(row["schema_version"]) is not int or row["schema_version"] != 1:
            raise GameplayContractError("unsupported NPC snapshot")
        if row["schedule_digest"] != schedule.digest:
            raise GameplayContractError("NPC snapshot source mismatch")
        commands = row["commands"]
        if type(commands) is not list or len(commands) > MAX_COMMANDS:
            raise GameplayContractError("invalid NPC replay length")
        session = cls.start(schedule)
        for raw_command in commands:
            session = session.apply(NpcCommand.parse(raw_command))
        if session.state_digest != row["state_digest"]:
            raise GameplayContractError("NPC replay digest mismatch")
        save_raw = _keys(row["save"], {"world_id", "schema_version", "tick",
                                      "state_digest", "canon_digest",
                                      "parent_save_digest"}, "save")
        save = SaveableGameplayState(**save_raw)
        if (save.world_id != schedule.world_id or save.schema_version != 1
                or save.tick != session.tick or save.state_digest != session.state_digest
                or save.canon_digest != schedule.canon_digest
                or save.digest != row["save_digest"]):
            raise GameplayContractError("NPC save integrity mismatch")
        return session


def play(schedule: NpcSchedule, commands: Sequence[Mapping[str, Any]],
         initial: NpcSession | None = None) -> NpcSession:
    session = initial if initial is not None else NpcSession.start(schedule)
    if session.schedule.digest != schedule.digest:
        raise GameplayContractError("NPC replay schedule mismatch")
    if len(commands) + len(session.commands) > MAX_COMMANDS:
        raise GameplayContractError("NPC replay budget exceeded")
    for command in commands:
        session = session.apply(NpcCommand.parse(command))
    return session
