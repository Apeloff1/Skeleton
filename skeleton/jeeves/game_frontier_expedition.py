"""Playable, deterministic multi-level expedition over original authored frontier worlds.

Real graph routing and progression for sky islands, ground regions, underwater
passages, climbing, updrafts, portals and vehicle links. An engine-neutral
simulation: it does not claim native Godot execution or use physical GPS.

The sole authority is the explicitly authored source graph and its digest.
Every transition is repeatable, source-bound and replay-auditable; routes
never invent an unconnected jump or bypass locked edge conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from heapq import heappop, heappush
import json
import math
import re
from typing import Mapping, Sequence

SCHEMA = "skeleton.game.frontier_expedition.v1"
SAVE_SCHEMA = "skeleton.game.frontier_expedition_save.v1"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_KINDS = frozenset((
    "ground", "sky_island", "underwater", "cavern", "airship",
    "ruins", "settlement", "canopy", "ice", "volcano",
))
_MODES = frozenset((
    "walk", "climb", "glide", "updraft", "swim", "dive",
    "airship", "portal", "rail", "boat", "rope_bridge",
))
_OBJECTIVES = ("fastest", "safest", "energy", "scenic")
_MAX_NODES, _MAX_LINKS, _MAX_ACTIONS = 8192, 65536, 65536


class ExpeditionError(ValueError):
    """Authored graph, route or episode violates a finite source contract."""


def _number(value: object, low: float, high: float, label: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise ExpeditionError(f"{label} must be a bounded finite number")
    return float(value)


def _int(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ExpeditionError(f"{label} must be a bounded integer")
    return value


def _id(value: object, name: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ExpeditionError(f"invalid {name}")
    return value


def _json(value: object, limit: int = 4_000_000) -> bytes:
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ExpeditionError("expedition data must be finite JSON") from exc
    if len(data) > limit:
        raise ExpeditionError("expedition exceeds canonical byte budget")
    return data


def _digest(value: object) -> str:
    return sha256(_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class Waypoint:
    waypoint_id: str
    x_m: float
    y_m: float
    altitude_m: float
    kind: str
    landmark: str = ""
    safe_rest: bool = False
    collectible: str = ""
    quest_flag: str = ""
    discovery_score: int = 1

    def __post_init__(self):
        _id(self.waypoint_id, "waypoint")
        for name, val in (("x", self.x_m), ("y", self.y_m), ("altitude", self.altitude_m)):
            _number(val, -1e6, 1e6, name)
        if self.kind not in _KINDS:
            raise ExpeditionError("waypoint kind not recognized")
        if type(self.landmark) is not str or len(self.landmark) > 256:
            raise ExpeditionError("landmark requires bounded original text")
        if type(self.safe_rest) is not bool:
            raise ExpeditionError("rest policy must be explicit")
        for name, value in (("collectible", self.collectible), ("quest", self.quest_flag)):
            if value:
                _id(value, name)
        _int(self.discovery_score, 0, 1000, "discovery score")


@dataclass(frozen=True, slots=True)
class TravelEdge:
    edge_id: str
    source: str
    target: str
    mode: str
    length_m: float
    duration_s: float
    stamina_cost: int
    risk: float = 0.0
    scenic_score: int = 0
    requires: tuple[str, ...] = ()
    grants: tuple[str, ...] = ()
    one_way: bool = True

    def __post_init__(self):
        for name in ("edge_id", "source", "target"):
            _id(getattr(self, name), name)
        if self.source == self.target:
            raise ExpeditionError("travel edge cannot loop to its own node")
        if self.mode not in _MODES:
            raise ExpeditionError("unsupported movement mode")
        _number(self.length_m, 0.01, 1e6, "edge length")
        _number(self.duration_s, 0.01, 1e6, "edge duration")
        _int(self.stamina_cost, 0, 100, "edge stamina")
        _number(self.risk, 0, 1, "edge risk")
        _int(self.scenic_score, 0, 1000, "edge scenery")
        if type(self.one_way) is not bool:
            raise ExpeditionError("one_way must be explicit")
        for values, name in ((self.requires, "requirements"), (self.grants, "grants")):
            if type(values) is not tuple or len(values) > 16:
                raise ExpeditionError(f"invalid {name}")
            if any(not isinstance(v, str) or not _ID.fullmatch(v) for v in values):
                raise ExpeditionError(f"invalid {name} identity")
            if len(set(values)) != len(values):
                raise ExpeditionError(f"duplicate {name}")


@dataclass(frozen=True, slots=True)
class ExpeditionWeather:
    wind_x_mps: float = 0.0
    wind_y_mps: float = 0.0
    vertical_mps: float = 0.0
    turbulence: float = 0.0
    rain: float = 0.0
    visibility: float = 1.0
    temperature_c: float = 20.0

    def __post_init__(self):
        for field_name, low, high in (
            ("wind_x_mps", -120, 120), ("wind_y_mps", -120, 120),
            ("vertical_mps", -50, 50), ("turbulence", 0, 1),
            ("rain", 0, 1), ("visibility", 0, 1),
            ("temperature_c", -100, 100),
        ):
            _number(getattr(self, field_name), low, high, field_name)


@dataclass(frozen=True, slots=True)
class Traveler:
    permitted_modes: frozenset[str] = frozenset(("walk", "rope_bridge"))
    flags: frozenset[str] = frozenset()
    equipment: frozenset[str] = frozenset()
    max_stamina: int = 100
    carried_kg: float = 0.0
    capacity_kg: float = 30.0
    skill: float = 0.5
    shelter: float = 0.0

    def __post_init__(self):
        for name in ("permitted_modes", "flags", "equipment"):
            value = getattr(self, name)
            if type(value) is not frozenset or len(value) > 128:
                raise ExpeditionError("traveler equipment, modes and flags must be bounded sets")
            if any(not isinstance(item, str) or not _ID.fullmatch(item.replace("-", "_"))
                   for item in value):
                raise ExpeditionError("invalid traveler capability identity")
        if not self.permitted_modes.issubset(_MODES):
            raise ExpeditionError("unimplemented movement mode")
        _int(self.max_stamina, 1, 1000, "stamina capacity")
        _number(self.carried_kg, 0, 10_000, "carried weight")
        _number(self.capacity_kg, 0.1, 10_000, "carry capacity")
        if self.carried_kg > self.capacity_kg:
            raise ExpeditionError("traveler is over capacity")
        _number(self.skill, 0, 1, "navigation skill")
        _number(self.shelter, 0, 1, "shelter protection")


@dataclass(frozen=True, slots=True)
class ExpeditionWorld:
    project_id: str
    source_digest: str
    waypoints: tuple[Waypoint, ...]
    edges: tuple[TravelEdge, ...]
    arrival: str
    destinations: tuple[str, ...]
    weather: ExpeditionWeather = field(default_factory=ExpeditionWeather)

    def __post_init__(self):
        _id(self.project_id, "project identity")
        if not isinstance(self.source_digest, str) or not _SHA.fullmatch(self.source_digest):
            raise ExpeditionError("expedition needs exact original source hash")
        if (type(self.waypoints) is not tuple or type(self.edges) is not tuple
                or not 2 <= len(self.waypoints) <= _MAX_NODES
                or not 1 <= len(self.edges) <= _MAX_LINKS):
            raise ExpeditionError("world navigation graph exceeds finite budgets")
        by_id = {node.waypoint_id: node for node in self.waypoints}
        if len(by_id) != len(self.waypoints):
            raise ExpeditionError("duplicate world waypoint")
        if len({e.edge_id for e in self.edges}) != len(self.edges):
            raise ExpeditionError("duplicate directed travel edge")
        if any(
            e.edge_id.endswith(".reverse") or
            (not e.one_way and e.edge_id+".reverse" in {x.edge_id for x in self.edges})
            for e in self.edges
        ):
            raise ExpeditionError("implicit reverse edge ID conflicts with authored source")
        for edge in self.edges:
            if edge.source not in by_id or edge.target not in by_id:
                raise ExpeditionError("travel connection references missing waypoint")
            if edge.mode == "updraft" and by_id[edge.target].altitude_m <= by_id[edge.source].altitude_m:
                raise ExpeditionError("updraft must lead to higher altitude")
            if edge.mode == "glide" and by_id[edge.target].altitude_m >= by_id[edge.source].altitude_m:
                raise ExpeditionError("glide must lose elevation")
            if edge.mode in {"walk", "rope_bridge", "rail"} and abs(
                    by_id[edge.target].altitude_m - by_id[edge.source].altitude_m
            ) > 6 and edge.mode == "walk":
                raise ExpeditionError("walking cannot teleport between elevations")
        if self.arrival not in by_id or not self.destinations:
            raise ExpeditionError("world requires a real source start and destination")
        if (type(self.destinations) is not tuple or len(self.destinations) > 128
                or len(set(self.destinations)) != len(self.destinations)
                or any(n not in by_id for n in self.destinations)):
            raise ExpeditionError("invalid world destination catalog")
        if not isinstance(self.weather, ExpeditionWeather):
            raise ExpeditionError("explicit typed fictional weather required")
        if len(_json(self.as_dict())) > 4_000_000:
            raise ExpeditionError("world source exceeds authored snapshot budget")

    @property
    def by_id(self) -> dict[str, Waypoint]:
        return {node.waypoint_id: node for node in self.waypoints}

    @property
    def by_edge(self) -> dict[str, TravelEdge]:
        from dataclasses import replace
        out={edge.edge_id: edge for edge in self.edges}
        for edge in self.edges:
            if not edge.one_way:
                reverse=replace(
                    edge,edge_id=edge.edge_id+".reverse",
                    source=edge.target,target=edge.source,one_way=True,
                )
                if reverse.edge_id in out:
                    raise ExpeditionError("reverse edge ID collides with authored edge")
                out[reverse.edge_id]=reverse
        return out

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return {
            "schema": SCHEMA, "project": self.project_id,
            "source": self.source_digest,
            "waypoints": [asdict(w) for w in self.waypoints],
            "edges": [asdict(e) for e in self.edges],
            "arrival": self.arrival, "destinations": list(self.destinations),
            "weather": asdict(self.weather),
            "device_location_used": False,
        }


@dataclass(frozen=True, slots=True)
class TravelAssessment:
    allowed: bool
    reason: str
    stamina: int
    duration_s: float
    damage: int
    wind_resistance: float
    traction: float

    @property
    def loss(self) -> int:
        return self.stamina + self.damage * 5


def assess_travel(
    world: ExpeditionWorld, edge: TravelEdge, traveler: Traveler, *,
    current_flags: frozenset[str] | None = None,
) -> TravelAssessment:
    """Evaluate actual directed travel costs and capability restrictions."""
    if edge.edge_id not in world.by_edge or world.by_edge[edge.edge_id] != edge:
        raise ExpeditionError("travel edge not part of this authored world")
    flags = traveler.flags if current_flags is None else current_flags
    if edge.mode not in traveler.permitted_modes:
        return TravelAssessment(False, "movement_mode_locked", 0, 0, 0, 0, 0)
    if not set(edge.requires).issubset(flags | traveler.equipment):
        return TravelAssessment(False, "required_ability_or_quest_flag", 0, 0, 0, 0, 0)
    src, dst = world.by_id[edge.source], world.by_id[edge.target]
    w = world.weather
    dx, dy = dst.x_m-src.x_m, dst.y_m-src.y_m
    length = math.hypot(dx, dy)
    wind_along = (
        (dx*w.wind_x_mps + dy*w.wind_y_mps) / length if length > 1e-8 else 0.0
    )
    aerial = edge.mode in {"glide", "updraft", "airship"}
    wet = edge.mode in {"walk", "climb", "rope_bridge"}
    pressure = (
        1.0 + max(0, -wind_along)*0.025
        + (w.turbulence*0.8 if aerial else 0)
        + (w.rain*0.5 if wet else 0)
    )
    if aerial and w.vertical_mps > 0 and edge.mode == "updraft":
        pressure = max(0.5, pressure - w.vertical_mps*0.02)
    traction = max(0.1, 1 - w.rain*(0.5 if wet else 0.1))
    mass_load = traveler.carried_kg/traveler.capacity_kg
    stamina = math.ceil(edge.stamina_cost * pressure * (
        1 + mass_load*0.6 - traveler.skill*0.2
    ))
    stamina = max(0, min(1000, stamina))
    # Hazard affects health separately; shelter & skills reduce risk, never
    # make a dangerous corridor risk-free without actual authored proof.
    exposure = (
        edge.risk*(1 + w.turbulence*0.7 + w.rain*0.4)
        *(1 - 0.45*traveler.skill)*(1 - 0.75*traveler.shelter)
    )
    damage = max(0, math.floor(exposure*10))
    duration = round(edge.duration_s * pressure * (1+mass_load*0.4), 4)
    if w.visibility < 0.12 and edge.mode in {"glide", "updraft", "airship", "portal"} and "instrument_navigation" not in traveler.equipment:
        return TravelAssessment(False, "visibility_requires_instruments", 0, 0, 0, 0, 0)
    return TravelAssessment(True, "passable", stamina, duration, damage, round(wind_along, 4), round(traction, 4))


@dataclass(frozen=True, slots=True)
class ExpeditionRoute:
    source: str
    destination: str
    edge_ids: tuple[str, ...]
    waypoints: tuple[str, ...]
    seconds: float
    stamina: int
    damage: int
    scenic_score: int
    objective: str
    world_digest: str

    @property
    def digest(self) -> str:
        from dataclasses import asdict
        return _digest(asdict(self))


def find_route(
    world: ExpeditionWorld,
    traveler: Traveler,
    destination: str,
    *,
    start: str | None = None,
    objective: str = "fastest",
    forbidden_edges: frozenset[str] = frozenset(),
    current_flags: frozenset[str] | None = None,
    current_stamina: int | None = None,
    max_expansions: int = 100000,
) -> ExpeditionRoute:
    """Dijkstra across exact positions and stamina (no invented connectivity).

    Route contains only executable directed travel links and obeys abilities,
    stamina and terrain conditions. Rest is not implicit; it is an explicit
    gameplay choice, so an exhausted route cannot be treated as traversable.
    """
    if objective not in _OBJECTIVES:
        raise ExpeditionError("unknown route optimization objective")
    if type(max_expansions) is not int or not 1 <= max_expansions <= 500000:
        raise ExpeditionError("bounded route search budget required")
    start = world.arrival if start is None else start
    if start not in world.by_id or destination not in world.by_id:
        raise ExpeditionError("route endpoint absent from authored world")
    available_stamina = traveler.max_stamina if current_stamina is None else _int(
        current_stamina, 0, traveler.max_stamina, "available stamina"
    )
    if start == destination:
        return ExpeditionRoute(start, destination, (), (start,), 0, 0, 0, 0, objective, world.digest)
    if type(forbidden_edges) is not frozenset:
        raise ExpeditionError("forbidden edge policy must be frozen")
    outgoing: dict[str, list[TravelEdge]] = {}
    for edge in world.by_edge.values():
        if edge.edge_id not in forbidden_edges:
            outgoing.setdefault(edge.source, []).append(edge)
    for entries in outgoing.values():
        entries.sort(key=lambda x: x.edge_id)
    initial_flags=frozenset(traveler.flags if current_flags is None else current_flags)
    initial = (start, available_stamina, initial_flags)
    distances: dict[tuple[str,int,frozenset[str]], float] = {initial: 0.0}
    parents: dict[
        tuple[str,int,frozenset[str]],
        tuple[tuple[str,int,frozenset[str]],str,TravelAssessment],
    ] = {}
    heap: list[tuple[float,int,str,int,frozenset[str]]] = [
        (0.0,0,start,available_stamina,initial_flags)
    ]
    serial=0
    reached=None
    expansions=0
    while heap:
        cost, _, pos, stamina, flags = heappop(heap)
        state=(pos,stamina,flags)
        if cost > distances.get(state,math.inf)+1e-8:
            continue
        if pos == destination:
            reached=state
            break
        expansions += 1
        if expansions > max_expansions:
            raise ExpeditionError("route solver exhausted finite search budget")
        for edge in outgoing.get(pos,()):
            assessed=assess_travel(world,edge,traveler,current_flags=flags)
            if not assessed.allowed or assessed.stamina>stamina:
                continue
            remains=stamina-assessed.stamina
            target=world.by_id[edge.target]
            grants=set(edge.grants)
            if edge.target != start:
                if target.quest_flag:
                    grants.add(target.quest_flag)
                if target.collectible:
                    grants.add(target.collectible)
            next_flags=flags | frozenset(grants)
            next_state=(edge.target,remains,next_flags)
            increment={
                "fastest":assessed.duration_s,
                "safest":assessed.damage*1_000 + assessed.duration_s*0.1 + edge.risk*100,
                "energy":assessed.stamina + assessed.duration_s*0.001,
                "scenic":assessed.duration_s/(1+edge.scenic_score)+assessed.damage*500,
            }[objective]
            new_cost=cost+max(0.000001,increment)
            if new_cost + 1e-8 < distances.get(next_state,math.inf):
                distances[next_state]=new_cost
                parents[next_state]=(state,edge.edge_id,assessed)
                serial+=1
                heappush(heap,(new_cost,serial,edge.target,remains,next_flags))
    if reached is None:
        raise ExpeditionError("no traversable route under current abilities and stamina")
    sequence=[]
    total_seconds=0.0
    total_damage=0
    total_scenery=0
    pointer=reached
    while pointer != initial:
        previous, eid, assessed=parents[pointer]
        sequence.append(eid)
        total_seconds+=assessed.duration_s
        total_damage+=assessed.damage
        total_scenery+=world.by_edge[eid].scenic_score
        pointer=previous
    sequence.reverse()
    positions=[start]
    for eid in sequence:
        positions.append(world.by_edge[eid].target)
    return ExpeditionRoute(
        start,destination,tuple(sequence),tuple(positions),
        round(total_seconds,4),available_stamina-reached[1],
        total_damage,total_scenery,objective,world.digest,
    )


def alternative_routes(
    world: ExpeditionWorld, traveler: Traveler, destination: str, *,
    start: str | None = None, limit: int = 8, objective: str = "fastest",
) -> tuple[ExpeditionRoute,...]:
    """Derive genuinely distinct connected routes via edge exclusions."""
    _int(limit,1,16,"route alternative budget")
    first=find_route(world,traveler,destination,start=start,objective=objective)
    unique={first.edge_ids:first}
    for edge_id in first.edge_ids:
        if len(unique)>=limit:
            break
        try:
            route=find_route(
                world,traveler,destination,start=start,objective=objective,
                forbidden_edges=frozenset((edge_id,)),
            )
        except ExpeditionError as exc:
            if str(exc)!="no traversable route under current abilities and stamina":
                raise
            continue
        unique.setdefault(route.edge_ids,route)
    return tuple(unique.values())


@dataclass(frozen=True, slots=True)
class ExpeditionAction:
    kind: str
    edge_id: str = ""

    def __post_init__(self):
        if self.kind not in {"travel","rest","inspect","interact"}:
            raise ExpeditionError("unsupported expedition action")
        if self.kind == "travel":
            _id(self.edge_id,"chosen travel edge")
        elif self.edge_id:
            raise ExpeditionError("nontravel action cannot smuggle edge identity")


class ExpeditionEpisode:
    """Real state mutation for one authored player expedition, with replay."""

    def __init__(self, world: ExpeditionWorld, traveler: Traveler, *,
                 health: int = 100):
        if not isinstance(world,ExpeditionWorld) or not isinstance(traveler,Traveler):
            raise ExpeditionError("typed world and traveler required")
        self.world=world
        self.traveler=traveler
        self.initial_health=_int(health,1,1000,"health")
        self.reset()

    def reset(self):
        self.position=self.world.arrival
        self.stamina=self.traveler.max_stamina
        self.health=self.initial_health
        self.seconds=0.0
        self.flags=set(self.traveler.flags)
        self.inventory=set()
        self.visited={self.position}
        self.actions:list[ExpeditionAction]=[]
        self.receipts:list[str]=[]
        self._head=_digest({
            "world":self.world.digest,"traveler":self.traveler_digest,
            "health":self.initial_health,"start":self.position,
        })
        return self.snapshot()

    @property
    def traveler_digest(self)->str:
        from dataclasses import asdict
        raw=asdict(self.traveler)
        raw["permitted_modes"]=sorted(self.traveler.permitted_modes)
        raw["flags"]=sorted(self.traveler.flags)
        raw["equipment"]=sorted(self.traveler.equipment)
        return _digest(raw)

    @property
    def won(self)->bool:
        return self.position in self.world.destinations and self.health>0

    @property
    def done(self)->bool:
        return self.won or self.health<=0 or len(self.actions)>=_MAX_ACTIONS

    def state(self)->dict:
        return {
            "position":self.position,"stamina":self.stamina,
            "health":self.health,"seconds":round(self.seconds,4),
            "flags":sorted(self.flags),"inventory":sorted(self.inventory),
            "visited":sorted(self.visited),"won":self.won,
            "actions":len(self.actions),
        }

    def step(self,action:ExpeditionAction)->dict:
        if not isinstance(action,ExpeditionAction):
            raise ExpeditionError("typed gameplay action required")
        if self.done:
            raise ExpeditionError("finished expedition may not silently continue")
        old=self.state()
        events=[]
        if action.kind=="travel":
            edge=self.world.by_edge.get(action.edge_id)
            if edge is None or edge.source!=self.position:
                raise ExpeditionError("travel must follow a connected outgoing edge")
            assessed=assess_travel(
                self.world,edge,self.traveler,
                current_flags=frozenset(self.flags),
            )
            if not assessed.allowed:
                raise ExpeditionError("travel blocked: "+assessed.reason)
            if self.stamina<assessed.stamina:
                raise ExpeditionError("insufficient actual stamina for chosen travel")
            self.stamina-=assessed.stamina
            self.health=max(0,self.health-assessed.damage)
            self.seconds=round(self.seconds+assessed.duration_s,4)
            self.position=edge.target
            self.flags.update(edge.grants)
            first_time=edge.target not in self.visited
            self.visited.add(edge.target)
            node=self.world.by_id[edge.target]
            if first_time:
                if node.collectible:
                    self.inventory.add(node.collectible)
                    events.append("collected:"+node.collectible)
                if node.quest_flag:
                    self.flags.add(node.quest_flag)
                    events.append("quest:"+node.quest_flag)
                events.append("discovered:"+edge.target)
            if self.health<=0:
                events.append("defeated")
            if self.won:
                events.append("destination_reached")
        elif action.kind=="rest":
            if not self.world.by_id[self.position].safe_rest:
                raise ExpeditionError("no authored rest site at current waypoint")
            before=self.stamina
            self.stamina=min(self.traveler.max_stamina,self.stamina+25)
            self.seconds=round(self.seconds+60,4)
            events.append("rested:"+str(self.stamina-before))
        elif action.kind=="interact":
            node=self.world.by_id[self.position]
            if not (node.landmark or node.collectible or node.quest_flag):
                raise ExpeditionError("waypoint has no authored interaction")
            if node.quest_flag:
                self.flags.add(node.quest_flag)
            if node.collectible:
                self.inventory.add(node.collectible)
            self.seconds=round(self.seconds+1,4)
            events.append("interacted:"+node.waypoint_id)
        elif action.kind=="inspect":
            self.seconds=round(self.seconds+0.1,4)
            events.append("inspected:"+self.position)
        previous=self._head
        self.actions.append(action)
        data={
            "index":len(self.actions),"previous":previous,
            "world":self.world.digest,"action":{"kind":action.kind,"edge":action.edge_id},
            "before":_digest(old),"after":_digest(self.state()),
            "events":events,
        }
        self._head=_digest(data)
        self.receipts.append(self._head)
        return {
            "schema":SCHEMA,"action":data["action"],"events":tuple(events),
            "state":self.state(),"receipt":self._head,"previous":previous,
            "done":self.done,"won":self.won,
        }

    def snapshot(self)->dict:
        payload={
            "schema":SAVE_SCHEMA,"world_digest":self.world.digest,
            "traveler_digest":self.traveler_digest,
            "health_initial":self.initial_health,
            "actions":[{"kind":a.kind,"edge_id":a.edge_id} for a in self.actions],
            "state_digest":_digest(self.state()),
            "receipt_head":self._head,"receipts":list(self.receipts),
        }
        return {**payload,"snapshot_digest":_digest(payload)}

    @classmethod
    def restore(cls,world:ExpeditionWorld,traveler:Traveler,
                snapshot:Mapping)->"ExpeditionEpisode":
        if not isinstance(snapshot,Mapping) or set(snapshot)!={
            "schema","world_digest","traveler_digest","health_initial",
            "actions","state_digest","receipt_head","receipts","snapshot_digest",
        }:
            raise ExpeditionError("snapshot schema or completeness differs")
        _json(dict(snapshot),2_000_000)
        data={k:v for k,v in snapshot.items() if k!="snapshot_digest"}
        if _digest(data)!=snapshot["snapshot_digest"]:
            raise ExpeditionError("expedition snapshot checksum was altered")
        if snapshot["schema"]!=SAVE_SCHEMA or snapshot["world_digest"]!=world.digest:
            raise ExpeditionError("expedition snapshot belongs to a different world")
        instance=cls(world,traveler,health=snapshot["health_initial"])
        if instance.traveler_digest!=snapshot["traveler_digest"]:
            raise ExpeditionError("traveler source changed since last checkpoint")
        actions=snapshot["actions"]
        if (not isinstance(actions,list) or len(actions)>_MAX_ACTIONS
                or not isinstance(snapshot["receipts"],list)
                or len(snapshot["receipts"])!=len(actions)):
            raise ExpeditionError("saved action ledger exceeds replay budget")
        for action in actions:
            if type(action) is not dict or set(action)!={"kind","edge_id"}:
                raise ExpeditionError("invalid immutable expedition action")
            instance.step(ExpeditionAction(**action))
        if (instance.receipts!=snapshot["receipts"]
                or instance._head!=snapshot["receipt_head"]
                or _digest(instance.state())!=snapshot["state_digest"]):
            raise ExpeditionError("replay diverged from the original game session")
        return instance


def verify_route(world:ExpeditionWorld, traveler:Traveler,
                 route:ExpeditionRoute)->dict:
    """Execute a suggested route on actual world-state machinery."""
    if route.world_digest!=world.digest or route.source!=world.arrival:
        raise ExpeditionError("route source or world is stale")
    episode=ExpeditionEpisode(world,traveler)
    actual=[]
    for edge in route.edge_ids:
        step=episode.step(ExpeditionAction("travel",edge))
        actual.append(step["receipt"])
    if episode.position!=route.destination:
        raise ExpeditionError("route ends at wrong actual waypoint")
    if tuple(route.waypoints)!=(world.arrival,)+tuple(
        world.by_edge[e].target for e in route.edge_ids
    ):
        raise ExpeditionError("route waypoints do not correspond to actual edges")
    return {
        "world":world.digest,"route":route.digest,
        "final_state":episode.state(),"receipt_head":episode._head,
        "step_receipts":actual,"verified":True,
        "authority":"engine_neutral_simulated_gameplay_not_native_godot",
    }


def world_export(world:ExpeditionWorld, *,
                 max_bytes:int=4_000_000)->dict:
    """Portable, fully source-bound original project data for an engine loader."""
    _int(max_bytes,256,4_000_000,"engine data budget")
    data=world.as_dict()
    data["world_digest"]=world.digest
    raw=_json(data,max_bytes)
    return {
        "schema":"skeleton.game.frontier_expedition_export.v1",
        "world_digest":world.digest,
        "data_sha256":sha256(raw).hexdigest(),
        "asset_path":"game/frontier/expedition.json",
        "content":raw.decode("utf-8"),
        "requires_native_loader":True,
    }
