"""Typed, fully deterministic world-state and conditional traversal primitives.

These types are inert without an explicitly authored dynamics block in a
reviewed Director world. Old worlds and journals serialize byte-for-byte
identically. No scripts, network, external providers, arbitrary file access,
unbounded expression interpreters or hidden dice can influence gameplay.

Gates restrict ordinary scene links; transit routes add legally executable
shortcuts, including ferries, portals, rail, airships, elevators and shuttles.
Influence events grant reputation on real interactions/quest conclusions.
Every permission is computed from immutable, journal-replayed state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
FLAGS = ("none", "local", "quest", "global")
MODES = ("foot", "rail", "ferry", "airship", "portal", "elevator", "shuttle",
         "taxi", "boat", "plane", "mount", "teleporter", "space", "underwater")
MAX_GATES = 1024
MAX_ROUTES = 2048
MAX_FACTIONS = 128
MAX_INFLUENCES = 4096
MAX_REPUTATION = 1000


def _id(value: Any) -> str:
    if type(value) is not str or ID.fullmatch(value) is None:
        raise ValueError("dynamic-world IDs must be 1..64 lower-case safe tokens")
    return value


def _text(value: Any, length: int = 300) -> str:
    if (type(value) is not str or not 1 <= len(value) <= length
            or value.strip() != value or any(ord(c) < 32 for c in value)):
        raise ValueError("dynamic-world narrative label must be printable and bounded")
    return value


def _number(value: Any, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("invalid dynamic-world amount or reputation threshold")
    return value


def _ids(values: Any, *, limit: int = 64) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)) or len(values) > limit:
        raise ValueError("invalid dynamic-world bounded identity list")
    result = tuple(_id(value) for value in values)
    if len(set(result)) != len(result):
        raise ValueError("duplicate dynamic-world identity")
    return result


def _strict(document: Any, keys: set[str], cls: str) -> dict:
    if type(document) is not dict or set(document) != keys:
        raise ValueError(cls + " schema must be exact, no unknown executable properties")
    return document


@dataclass(frozen=True, slots=True)
class StandingRequirement:
    faction: str
    at_least: int = -1000
    at_most: int = 1000

    def __post_init__(self):
        _id(self.faction)
        _number(self.at_least, -MAX_REPUTATION, MAX_REPUTATION)
        _number(self.at_most, -MAX_REPUTATION, MAX_REPUTATION)
        if self.at_least > self.at_most:
            raise ValueError("faction minimum exceeds maximum standing")

    def payload(self):
        return {"faction": self.faction, "at_least": self.at_least,
                "at_most": self.at_most}


@dataclass(frozen=True, slots=True)
class Requirements:
    items: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    quests: tuple[str, ...] = ()
    world_flags: tuple[str, ...] = ()
    standings: tuple[StandingRequirement, ...] = ()
    forbidden_flags: tuple[str, ...] = ()
    forbidden_world_flags: tuple[str, ...] = ()

    def __post_init__(self):
        for group in (self.items, self.flags, self.quests, self.world_flags,
                      self.forbidden_flags, self.forbidden_world_flags):
            _ids(group)
        if set(self.flags) & set(self.forbidden_flags):
            raise ValueError("a gate cannot simultaneously require and forbid a flag")
        if set(self.world_flags) & set(self.forbidden_world_flags):
            raise ValueError("a gate cannot both require and forbid a world event")
        if not isinstance(self.standings, tuple) or len(self.standings) > 64:
            raise ValueError("too many standing conditions")
        if any(not isinstance(s, StandingRequirement) for s in self.standings):
            raise ValueError("invalid standing condition")
        if len({s.faction for s in self.standings}) != len(self.standings):
            raise ValueError("duplicate faction threshold")

    def payload(self):
        return {
            "items": list(self.items), "flags": list(self.flags),
            "quests": list(self.quests), "world_flags": list(self.world_flags),
            "standings": [s.payload() for s in self.standings],
            "forbidden_flags": list(self.forbidden_flags),
            "forbidden_world_flags": list(self.forbidden_world_flags),
        }


@dataclass(frozen=True, slots=True)
class Faction:
    key: str
    name: str
    starting_standing: int = 0

    def __post_init__(self):
        _id(self.key)
        _text(self.name, 180)
        _number(self.starting_standing, -MAX_REPUTATION, MAX_REPUTATION)

    def payload(self):
        return {"key": self.key, "name": self.name,
                "starting_standing": self.starting_standing}


@dataclass(frozen=True, slots=True)
class Passage:
    key: str
    source: str
    destination: str
    mode: str = "portal"
    name: str = "An original passage"
    cost_turns: int = 1
    requirements: Requirements = Requirements()
    consume_item: str | None = None
    grant_world_flag: str | None = None
    reputation_change: tuple[tuple[str, int], ...] = ()
    bidirectional: bool = False

    def __post_init__(self):
        for value in (self.key, self.source, self.destination):
            _id(value)
        if self.source == self.destination:
            raise ValueError("passage must connect different scenes")
        if self.mode not in MODES:
            raise ValueError("unknown authored transport type")
        _text(self.name)
        _number(self.cost_turns, 1, 180)
        if not isinstance(self.requirements, Requirements):
            raise ValueError("passage requires typed conditions")
        if self.consume_item is not None:
            _id(self.consume_item)
            if self.consume_item not in self.requirements.items:
                raise ValueError("consumed ticket must be a gate requirement")
        if self.grant_world_flag is not None:
            _id(self.grant_world_flag)
        if type(self.bidirectional) is not bool:
            raise ValueError("passage direction must be explicit")
        if (not isinstance(self.reputation_change, tuple)
                or len(self.reputation_change) > 16):
            raise ValueError("invalid passage faction effects")
        for faction, value in self.reputation_change:
            _id(faction)
            _number(value, -200, 200)
        if len({f for f, _ in self.reputation_change}) != len(self.reputation_change):
            raise ValueError("passage repeats a faction effect")

    def payload(self):
        return {
            "key": self.key, "source": self.source,
            "destination": self.destination, "mode": self.mode, "name": self.name,
            "cost_turns": self.cost_turns,
            "requirements": self.requirements.payload(),
            "consume_item": self.consume_item,
            "grant_world_flag": self.grant_world_flag,
            "reputation_change": [[f, amount] for f, amount in self.reputation_change],
            "bidirectional": self.bidirectional,
        }


@dataclass(frozen=True, slots=True)
class Gate:
    source: str
    destination: str
    requirements: Requirements = Requirements()
    label: str = "A conditional passage"

    def __post_init__(self):
        _id(self.source)
        _id(self.destination)
        if self.source == self.destination:
            raise ValueError("gate cannot guard a self-loop")
        if not isinstance(self.requirements, Requirements):
            raise ValueError("gate requires typed conditions")
        _text(self.label)

    def payload(self):
        return {"source": self.source, "destination": self.destination,
                "requirements": self.requirements.payload(), "label": self.label}


@dataclass(frozen=True, slots=True)
class Influence:
    key: str
    trigger: str
    faction: str
    delta: int = 0
    scene: str | None = None
    affordance: str | None = None
    quest: str | None = None
    outcome_flag: str | None = None
    grant_world_flag: str | None = None
    once: bool = True

    def __post_init__(self):
        _id(self.key)
        if self.trigger not in {"use", "quest_result"}:
            raise ValueError("influence requires a real gameplay trigger")
        _id(self.faction)
        _number(self.delta, -200, 200)
        for field in (self.scene, self.affordance, self.quest,
                      self.outcome_flag, self.grant_world_flag):
            if field is not None:
                _id(field)
        if (self.trigger == "use" and (self.scene is None or self.affordance is None
                                         or self.quest is not None or self.outcome_flag is not None)):
            raise ValueError("use influence needs one authored scene and affordance")
        if (self.trigger == "quest_result" and
                (self.quest is None or self.scene is not None or self.affordance is not None)):
            raise ValueError("quest result influence needs a quest target")
        if type(self.once) is not bool:
            raise ValueError("reputation repeat policy must be explicit")

    def payload(self):
        return {
            "key": self.key, "trigger": self.trigger, "faction": self.faction,
            "delta": self.delta, "scene": self.scene,
            "affordance": self.affordance, "quest": self.quest,
            "outcome_flag": self.outcome_flag,
            "grant_world_flag": self.grant_world_flag, "once": self.once,
        }


@dataclass(frozen=True, slots=True)
class WorldDynamics:
    factions: tuple[Faction, ...] = ()
    gates: tuple[Gate, ...] = ()
    passages: tuple[Passage, ...] = ()
    influences: tuple[Influence, ...] = ()

    def __post_init__(self):
        checks = ((self.factions, Faction, MAX_FACTIONS),
                  (self.gates, Gate, MAX_GATES),
                  (self.passages, Passage, MAX_ROUTES),
                  (self.influences, Influence, MAX_INFLUENCES))
        for records, typ, limit in checks:
            if not isinstance(records, tuple) or len(records) > limit:
                raise ValueError("dynamic-world structure exceeds bounded export batch")
            if any(not isinstance(r, typ) for r in records):
                raise ValueError("dynamic-world record must be typed")
        for records in (self.factions, self.passages, self.influences):
            if len({r.key for r in records}) != len(records):
                raise ValueError("duplicate authored world-dynamics key")
        if len({(g.source, g.destination) for g in self.gates}) != len(self.gates):
            raise ValueError("duplicate authored link gate")
        known = {f.key for f in self.factions}
        for gate in self.gates:
            for standing in gate.requirements.standings:
                if standing.faction not in known:
                    raise ValueError("gate references non-existent faction")
        for passage in self.passages:
            for standing in passage.requirements.standings:
                if standing.faction not in known:
                    raise ValueError("transit references non-existent faction")
            if any(f not in known for f, _ in passage.reputation_change):
                raise ValueError("passage alters non-existent faction")
        for influence in self.influences:
            if influence.faction not in known:
                raise ValueError("influence references non-existent faction")

    def payload(self):
        return {
            "schema": "skeleton.game_builder.world_dynamics.v1",
            "factions": [x.payload() for x in self.factions],
            "gates": [x.payload() for x in self.gates],
            "passages": [x.payload() for x in self.passages],
            "influences": [x.payload() for x in self.influences],
        }


@dataclass(frozen=True, slots=True)
class WorldState:
    standings: tuple[tuple[str, int], ...] = ()
    world_flags: tuple[str, ...] = ()
    fired_influences: tuple[str, ...] = ()
    passage_uses: tuple[tuple[str, int], ...] = ()

    def __post_init__(self):
        _ids(self.world_flags, limit=4096)
        _ids(self.fired_influences, limit=4096)
        if len(self.standings) > MAX_FACTIONS:
            raise ValueError("world contains excessive faction standing entries")
        if len({f for f, _ in self.standings}) != len(self.standings):
            raise ValueError("duplicate saved standing")
        for faction, value in self.standings:
            _id(faction)
            _number(value, -MAX_REPUTATION, MAX_REPUTATION)
        if len({key for key, _ in self.passage_uses}) != len(self.passage_uses):
            raise ValueError("duplicate passage-use counter")
        for key, value in self.passage_uses:
            _id(key)
            _number(value, 1, 100_000_000)

    def payload(self):
        return {
            "standings": [[f, n] for f, n in self.standings],
            "world_flags": list(self.world_flags),
            "fired_influences": list(self.fired_influences),
            "passage_uses": [[p, n] for p, n in self.passage_uses],
        }


def initial(dynamics: WorldDynamics) -> WorldState:
    if not isinstance(dynamics, WorldDynamics):
        raise ValueError("typed world dynamics required")
    return WorldState(
        standings=tuple(sorted((f.key, f.starting_standing)
                               for f in dynamics.factions)),
    )


def permits(requirements: Requirements, state: Any) -> bool:
    """Only inspect canonically earned items, quest results, flags and standing."""
    if not isinstance(requirements, Requirements):
        raise ValueError("invalid world passage requirements")
    status: WorldState = state.world_state
    if status is None:
        return False
    inventory = set(state.acquired)
    flags = set(state.narrative_flags)
    completed = set(state.complete)
    world_flags = set(status.world_flags)
    standing = dict(status.standings)
    return (
        set(requirements.items).issubset(inventory)
        and set(requirements.flags).issubset(flags)
        and set(requirements.quests).issubset(completed)
        and set(requirements.world_flags).issubset(world_flags)
        and not set(requirements.forbidden_flags).intersection(flags)
        and not set(requirements.forbidden_world_flags).intersection(world_flags)
        and all(s.at_least <= standing[s.faction] <= s.at_most
                for s in requirements.standings)
    )


def gate_for(dynamics: WorldDynamics, start: str, end: str) -> Gate | None:
    return next((g for g in dynamics.gates
                 if g.source == start and g.destination == end), None)


def allowed_foot_travel(dynamics: WorldDynamics, state: Any, destination: str) -> bool:
    gate = gate_for(dynamics, state.scene, destination)
    return gate is None or permits(gate.requirements, state)


def offered_passages(dynamics: WorldDynamics, state: Any) -> tuple[Passage, ...]:
    return tuple(
        passage for passage in dynamics.passages
        if (passage.source == state.scene
            or passage.bidirectional and passage.destination == state.scene)
        and permits(passage.requirements, state)
    )


def apply_changes(status: WorldState, effects: tuple[tuple[str, int], ...] = (),
                  *, add_flags: tuple[str, ...] = (),
                  fired: tuple[str, ...] = (),
                  passage: str | None = None) -> WorldState:
    standing = dict(status.standings)
    for faction, delta in effects:
        if faction not in standing:
            raise ValueError("influence references untracked faction")
        standing[faction] = max(-MAX_REPUTATION, min(
            MAX_REPUTATION, standing[faction] + delta))
    usage = dict(status.passage_uses)
    if passage is not None:
        usage[passage] = usage.get(passage, 0) + 1
        if usage[passage] > 100_000_000:
            raise ValueError("passage counter would exceed validated range")
    return WorldState(
        standings=tuple(sorted(standing.items())),
        world_flags=tuple(sorted(set(status.world_flags) | set(add_flags))),
        fired_influences=tuple(sorted(set(status.fired_influences) | set(fired))),
        passage_uses=tuple(sorted(usage.items())),
    )


def effects_for_use(dynamics: WorldDynamics, status: WorldState, *,
                    scene: str, affordance: str) -> tuple[tuple[tuple[str, int], ...],
                                                         tuple[str, ...], tuple[str, ...]]:
    deltas, flags, fired = [], [], []
    for effect in dynamics.influences:
        if effect.trigger != "use" or effect.scene != scene or effect.affordance != affordance:
            continue
        if effect.once and effect.key in status.fired_influences:
            continue
        deltas.append((effect.faction, effect.delta))
        if effect.grant_world_flag:
            flags.append(effect.grant_world_flag)
        if effect.once:
            fired.append(effect.key)
    return tuple(deltas), tuple(flags), tuple(fired)


def effects_for_results(dynamics: WorldDynamics, status: WorldState, *,
                        results: tuple[Any, ...]) -> tuple[tuple[tuple[str, int], ...],
                                                          tuple[str, ...], tuple[str, ...]]:
    deltas, flags, fired = [], [], []
    for effect in dynamics.influences:
        if effect.trigger != "quest_result":
            continue
        if effect.once and effect.key in status.fired_influences:
            continue
        for result in results:
            if result.quest != effect.quest:
                continue
            if effect.outcome_flag is not None and (
                    result.consequence != effect.quest + "_" + effect.outcome_flag):
                continue
            deltas.append((effect.faction, effect.delta))
            if effect.grant_world_flag:
                flags.append(effect.grant_world_flag)
            if effect.once:
                fired.append(effect.key)
            break
    return tuple(deltas), tuple(flags), tuple(fired)


def compile_dynamics(data: Any) -> WorldDynamics:
    """Reject ambiguous or executable JSON; never eval a permission expression."""
    doc = _strict(data, {"schema", "factions", "gates", "passages", "influences"},
                  "world-dynamics")
    if doc["schema"] != "skeleton.game_builder.world_dynamics.v1":
        raise ValueError("unknown world-dynamics version")
    def requirements(entry: Any) -> Requirements:
        row = _strict(entry, {"items", "flags", "quests", "world_flags",
                              "standings", "forbidden_flags",
                              "forbidden_world_flags"}, "passage condition")
        standings = tuple(StandingRequirement(
            **_strict(x, {"faction", "at_least", "at_most"},
                      "reputation threshold")) for x in row["standings"])
        return Requirements(
            items=_ids(row["items"]), flags=_ids(row["flags"]),
            quests=_ids(row["quests"]), world_flags=_ids(row["world_flags"]),
            forbidden_flags=_ids(row["forbidden_flags"]),
            forbidden_world_flags=_ids(row["forbidden_world_flags"]),
            standings=standings,
        )

    factions = tuple(Faction(**_strict(f, {"key", "name", "starting_standing"},
                                       "faction")) for f in doc["factions"])
    gates = tuple(Gate(
        source=_strict(g, {"source", "destination", "label", "requirements"},
                       "guarded path")["source"],
        destination=g["destination"], label=g["label"],
        requirements=requirements(g["requirements"])
    ) for g in doc["gates"])
    passages = tuple(Passage(
        key=_strict(p, {"key", "source", "destination", "mode", "name",
                         "cost_turns", "requirements", "consume_item",
                         "grant_world_flag", "reputation_change",
                         "bidirectional"}, "transit route")["key"],
        source=p["source"], destination=p["destination"],
        mode=p["mode"], name=p["name"], cost_turns=p["cost_turns"],
        requirements=requirements(p["requirements"]),
        consume_item=p["consume_item"],
        grant_world_flag=p["grant_world_flag"],
        reputation_change=tuple(tuple(pair) for pair in p["reputation_change"]),
        bidirectional=p["bidirectional"],
    ) for p in doc["passages"])
    influences = tuple(Influence(**_strict(
        entry, {"key", "trigger", "faction", "delta", "scene", "affordance",
                "quest", "outcome_flag", "grant_world_flag", "once"},
        "reputation influence")) for entry in doc["influences"])
    return WorldDynamics(factions, gates, passages, influences)
