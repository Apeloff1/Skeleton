"""Bounded universal original-game route graph and executable planning semantics.

Supports long/impractical routes, detours, dead-ends, cycles, shortcuts,
hidden/secret/unlockable paths, free roaming, environmental conditions,
weather schedules, capability gates, money, fatigue, clue acquisition,
transport and fictional/space traversal.

All paths are *actual graph transitions* with replayable state/resource
evidence. A registry mode alone does not claim platform-specific physics.
No maps, copyrighted levels, imagery or publisher IP are imported.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from hashlib import sha256
from heapq import heappop,heappush
from itertools import count
import json,re

from .dragon_route_taxonomy import MODES,ROUTE_SHAPES,ENVIRONMENT_FLAGS

SCHEMA="skeleton.ai.dragon.universal_routes.v1"
MAX_NODES=48
MAX_EDGES=192
MAX_HOPS=80
MAX_EXPANSIONS=60000
MAX_MINUTES=26_280_000  # 50 years of actual in-game travel time
MAX_EDGE_MINUTES=10_512_000  # 20 years per abstract leg; still int32-safe
VALID_ID=re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
OBJECTIVES=("fastest","cheapest","safest","least_exhausting","scenic",
            "exploratory","challenging","impractical","balanced")
METRIC_FIELDS=("minutes","money_spent","risk","energy_used","sights")

def _ids(values,*,limit=20):
    if not isinstance(values,(tuple,frozenset)) or len(values)>limit:
        raise ValueError("game route tokens outside bounded immutable set")
    if any(type(x) is not str or not VALID_ID.fullmatch(x) for x in values):
        raise ValueError("route token names must be neutral original identifiers")
    if len(set(values))!=len(values):
        raise ValueError("duplicate original route token")

def _number(v,low,high,reason):
    if type(v) is not int or not low<=v<=high:
        raise ValueError("invalid original game route "+reason)

@dataclass(frozen=True)
class Place:
    id:str
    region:str="world"
    biome:str="temperate"
    gifts:tuple[str,...]=()
    energy_refill:int=0
    money_pickup:int=0
    scenic_value:int=0
    tags:tuple[str,...]=()

@dataclass(frozen=True)
class Traverse:
    id:str
    origin:str
    destination:str
    mode:str
    shapes:tuple[str,...]=()
    minutes:int=10
    price:int=0
    fatigue:int=1
    danger:int=0
    spectacle:int=0
    requires:tuple[str,...]=()
    requires_one:tuple[str,...]=()
    grants:tuple[str,...]=()
    consumes:tuple[str,...]=()
    weather_any:tuple[str,...]=()
    weather_none:tuple[str,...]=()
    departures:tuple[int,...]=()
    secret_token:str=""
    hazard_resistance:str=""
    one_way:bool=True
    fuel:int=0
    oxygen:int=0
    mana:int=0

@dataclass(frozen=True)
class World:
    places:tuple[Place,...]
    connections:tuple[Traverse,...]
    start:str
    goal:str
    environment:tuple[str,...]=("clear",)
    original_work_attested:bool=True
    source_origin:str="generated_original"
    max_minutes:int=MAX_MINUTES
    schema:str=SCHEMA

@dataclass(frozen=True)
class Traveller:
    tokens:frozenset[str]=frozenset()
    cash:int=200
    energy:int=100
    max_energy:int=100
    start_minute:int=480
    fuel:int=60
    oxygen:int=60
    mana:int=60

@dataclass(frozen=True)
class Waypoint:
    place:str
    tokens:frozenset[str]
    money:int
    energy:int
    clock:int
    elapsed:int
    visits:int
    requirements:int
    route:tuple[str,...]
    movement_minutes:int
    waiting_minutes:int
    spent:int
    danger:int
    fatigue:int
    spectacle:int
    traversed_places:tuple[str,...]
    fuel:int
    oxygen:int
    mana:int
    fuel_spent:int
    oxygen_spent:int
    mana_spent:int

@dataclass(frozen=True)
class Journey:
    schema:str
    objective:str
    edges:tuple[str,...]
    places:tuple[str,...]
    modes:tuple[str,...]
    shapes:tuple[str,...]
    length:int
    movement_minutes:int
    waiting_minutes:int
    elapsed_minutes:int
    money_spent:int
    risk:int
    energy_used:int
    sights:int
    loops:int
    visited_places:int
    secret_edges:int
    unlockable_edges:int
    environmental_edges:int
    success:bool
    original_content_only:bool
    digest:str
    fuel_used:int=0
    oxygen_used:int=0
    mana_used:int=0

@dataclass(frozen=True)
class RouteSearch:
    schema:str
    start:str
    goal:str
    environment:tuple[str,...]
    objective:str
    routes:tuple[Journey,...]
    examined_states:int
    truncated:bool
    solver:str
    claims:str


def validate_world(world:World)->None:
    if not isinstance(world,World) or world.schema!=SCHEMA:
        raise ValueError("unknown original world graph schema")
    if world.original_work_attested is not True or world.source_origin!="generated_original":
        raise PermissionError("original world route source and content rights not attested")
    if not isinstance(world.places,tuple) or not 2<=len(world.places)<=MAX_NODES:
        raise ValueError("world size must be 2..48 original places")
    if not isinstance(world.connections,tuple) or not 1<=len(world.connections)<=MAX_EDGES:
        raise ValueError("world route count outside bounded graph size")
    _number(world.max_minutes,1,MAX_MINUTES,"time horizon")
    _ids(world.environment,limit=len(ENVIRONMENT_FLAGS))
    if any(flag not in ENVIRONMENT_FLAGS for flag in world.environment):
        raise ValueError("unknown environmental physics state")
    names=set()
    for node in world.places:
        if not isinstance(node,Place) or not VALID_ID.fullmatch(node.id) or node.id in names:
            raise ValueError("place identity duplicated or invalid")
        names.add(node.id)
        if any(type(x) is not str or not VALID_ID.fullmatch(x)
               for x in (node.region,node.biome)):
            raise ValueError("place region/biome identifier invalid")
        _ids(node.gifts)
        _ids(node.tags)
        _number(node.energy_refill,0,100,"energy pickup")
        _number(node.money_pickup,0,10000,"money pickup")
        _number(node.scenic_value,0,100,"scenery")
    if world.start not in names or world.goal not in names or world.start==world.goal:
        raise ValueError("original game requires separate real start and goal")
    known=set()
    for edge in world.connections:
        if not isinstance(edge,Traverse) or not VALID_ID.fullmatch(edge.id) or edge.id in known:
            raise ValueError("route edge is unnamed or duplicated")
        known.add(edge.id)
        if edge.origin not in names or edge.destination not in names or edge.origin==edge.destination:
            raise ValueError("route needs actual different world locations")
        if edge.mode not in MODES:
            raise ValueError("unregistered world traversal mode")
        if (not isinstance(edge.shapes,tuple) or
                any(x not in ROUTE_SHAPES for x in edge.shapes)):
            raise ValueError("route classification outside original game vocabulary")
        _ids(edge.shapes,limit=16)
        for field,high in (("minutes",MAX_EDGE_MINUTES),("price",10000),
                           ("fatigue",100),("danger",100),
                           ("spectacle",100),("fuel",100),
                           ("oxygen",100),("mana",100)):
            _number(getattr(edge,field),1 if field=="minutes" else 0,high,field)
        for field in ("requires","requires_one","grants","consumes"):
            _ids(getattr(edge,field))
        for field in ("weather_any","weather_none"):
            flags=getattr(edge,field)
            _ids(flags,limit=len(ENVIRONMENT_FLAGS))
            if any(flag not in ENVIRONMENT_FLAGS for flag in flags):
                raise ValueError("route condition references unknown weather")
        if not isinstance(edge.departures,tuple) or len(edge.departures)>24:
            raise ValueError("route departure timetable exceeds daily schedule")
        for minute in edge.departures:
            _number(minute,0,1439,"departure minute")
        if len(set(edge.departures))!=len(edge.departures):
            raise ValueError("duplicated route departure")
        if edge.secret_token and not VALID_ID.fullmatch(edge.secret_token):
            raise ValueError("hidden path discovery token invalid")
        if edge.hazard_resistance and not VALID_ID.fullmatch(edge.hazard_resistance):
            raise ValueError("environment protection token invalid")
        if type(edge.one_way) is not bool:
            raise ValueError("one-way traversal must be explicit")
        if ("secret" in edge.shapes or "secret_unlockable" in edge.shapes or
            "hidden" in edge.shapes) and not edge.secret_token:
            raise ValueError("secret path must have a discoverable non-public gate")
        if "unlockable" in edge.shapes and not edge.requires:
            raise ValueError("unlockable route requires actual key/token")
    # Every ordinary undeclared reverse edge really is one way; no implicit
    # teleport or two-way assumption. Explicit two-way convenience is rejected
    # until the opposite directed transition exists, to avoid false reachability.
    pair={(x.origin,x.destination,x.mode) for x in world.connections}
    for edge in world.connections:
        if not edge.one_way and (edge.destination,edge.origin,edge.mode) not in pair:
            raise ValueError("bidirectional route missing actual reverse transition")


def validate_traveller(traveller:Traveller):
    if not isinstance(traveller,Traveller):
        raise ValueError("missing playable traveller state")
    _ids(traveller.tokens,limit=64)
    _number(traveller.cash,0,100000,"starting currency")
    _number(traveller.max_energy,1,1000,"maximum stamina")
    _number(traveller.energy,0,traveller.max_energy,"starting stamina")
    _number(traveller.start_minute,0,10080,"starting clock")
    _number(traveller.fuel,0,1000,"starting fuel")
    _number(traveller.oxygen,0,1000,"starting oxygen")
    _number(traveller.mana,0,1000,"starting magic resource")


def _node_index(world:World):
    return {place.id:i for i,place in enumerate(world.places)}

def _depart(edge:Traverse,clock:int):
    if not edge.departures:return 0
    current=clock%1440
    return min((depart-current)%1440 for depart in edge.departures)

def _begin(world:World,traveller:Traveller)->Waypoint:
    index=_node_index(world)
    start=world.places[index[world.start]]
    return Waypoint(
        world.start,traveller.tokens|frozenset(start.gifts),
        min(100000,traveller.cash+start.money_pickup),
        min(traveller.max_energy,traveller.energy+start.energy_refill),
        traveller.start_minute,0,1<<index[world.start],0,(),
        0,0,0,0,0,start.scenic_value,(world.start,),
        traveller.fuel,traveller.oxygen,traveller.mana,0,0,0,
    )

def _apply(world:World,traveller:Traveller,state:Waypoint,edge:Traverse,
           idx:dict[str,int],requirements:tuple[str,...])->Waypoint|None:
    if edge.origin!=state.place:return None
    tokens=state.tokens
    if not set(edge.requires).issubset(tokens):return None
    if edge.requires_one and not set(edge.requires_one).intersection(tokens):return None
    if edge.secret_token and edge.secret_token not in tokens:return None
    if edge.hazard_resistance and edge.hazard_resistance not in tokens:return None
    if edge.consumes and not set(edge.consumes).issubset(tokens):return None
    conditions=set(world.environment)
    if edge.weather_any and not conditions.intersection(edge.weather_any):return None
    if edge.weather_none and conditions.intersection(edge.weather_none):return None
    waiting=_depart(edge,state.clock)
    if state.elapsed+waiting+edge.minutes>world.max_minutes:return None
    if (state.money<edge.price or state.energy<edge.fatigue or
            state.fuel<edge.fuel or state.oxygen<edge.oxygen or
            state.mana<edge.mana):return None
    if len(state.route)>=MAX_HOPS:return None
    target=world.places[idx[edge.destination]]
    bit=1<<idx[edge.destination]
    first_visit=(state.visits&bit)==0
    new_tokens=(tokens-set(edge.consumes))|set(edge.grants)
    if first_visit:new_tokens|=set(target.gifts)
    added_money=target.money_pickup if first_visit else 0
    added_energy=target.energy_refill if first_visit else 0
    requirement_mask=state.requirements
    for number,term in enumerate(requirements):
        if term.startswith("mode:"):
            found=edge.mode==term[5:]
        elif term.startswith("family:"):
            found=MODES[edge.mode]==term[7:]
        elif term.startswith("shape:"):
            found=term[6:] in edge.shapes
        elif term.startswith("place:"):
            found=term[6:]==target.id
        else:
            found=False
        if found:requirement_mask|=1<<number
    return Waypoint(
        edge.destination,frozenset(new_tokens),
        min(100000,state.money-edge.price+added_money),
        min(traveller.max_energy,state.energy-edge.fatigue+added_energy),
        state.clock+waiting+edge.minutes,
        state.elapsed+waiting+edge.minutes,state.visits|bit,
        requirement_mask,state.route+(edge.id,),
        state.movement_minutes+edge.minutes,state.waiting_minutes+waiting,
        state.spent+edge.price,state.danger+edge.danger,
        state.fatigue+edge.fatigue,
        state.spectacle+edge.spectacle+(target.scenic_value if first_visit else 0),
        state.traversed_places+(edge.destination,),
        state.fuel-edge.fuel,state.oxygen-edge.oxygen,state.mana-edge.mana,
        state.fuel_spent+edge.fuel,state.oxygen_spent+edge.oxygen,
        state.mana_spent+edge.mana,
    )

def _cost(edge:Traverse,wait:int,objective:str,reused:int)->int:
    if objective=="fastest":base=edge.minutes+wait
    elif objective=="cheapest":base=1+edge.price*25+edge.minutes//10
    elif objective=="safest":base=1+edge.danger*30+(edge.minutes+wait)//12
    elif objective=="least_exhausting":base=1+edge.fatigue*30+(edge.minutes+wait)//15
    elif objective=="scenic":base=104-edge.spectacle+edge.minutes//20
    elif objective=="exploratory":base=45-edge.spectacle//3+edge.minutes//30
    elif objective=="challenging":base=104-edge.danger+edge.minutes//20
    elif objective=="impractical":base=12+edge.minutes//100
    elif objective=="balanced":base=1+edge.minutes//5+edge.price+edge.danger*2
    else:raise ValueError("unknown original-world routing objective")
    # Positive cost means every edge is actually traversed. Discourage
    # duplicate search solutions instead of inventing route differences.
    return max(1,base)+reused*18

def _requirements(items:tuple[str,...])->None:
    if not isinstance(items,tuple) or len(items)>8 or len(set(items))!=len(items):
        raise ValueError("original routing milestones must be unique and bounded")
    for item in items:
        if not isinstance(item,str) or not (
                item.startswith(("mode:","family:","shape:","place:")) and
                item.count(":")==1):
            raise ValueError("route milestone must name a mode/family/shape/place")
        kind,name=item.split(":")
        if not VALID_ID.fullmatch(name):
            raise ValueError("route milestone identifier is unsafe")
        if (kind=="mode" and name not in MODES or
            kind=="family" and name not in set(MODES.values()) or
            kind=="shape" and name not in ROUTE_SHAPES):
            raise ValueError("unrecognized original route milestone")

def plan(world:World,traveller:Traveller=Traveller(),*,
         objective:str="fastest",requires:tuple[str,...]=(),
         minimum_minutes:int=0,avoid:tuple[str,...]=(),
         expansion_cap:int=8000)->tuple[Journey|None,int,bool]:
    """Deterministic bounded graph search: time, money, unlocks, fatigue, routes.

    Uses fixed nonnegative multiobjective scalarization for each solver.
    Long/impractical routes can require actual elapsed minutes and waypoints.
    Infinite loops and rest farming cannot create unlimited currency/energy.
    """
    validate_world(world)
    validate_traveller(traveller)
    if objective not in OBJECTIVES:raise ValueError("unknown game route solver objective")
    _number(minimum_minutes,0,world.max_minutes,"minimum journey duration")
    _number(expansion_cap,100,MAX_EXPANSIONS,"search state budget")
    _requirements(requires)
    _ids(avoid,limit=MAX_EDGES)
    edges={item.id:item for item in world.connections}
    if any(x not in edges for x in avoid):
        raise ValueError("diversity penalty references nonexistent route edges")
    outgoing={}
    for edge in world.connections:
        outgoing.setdefault(edge.origin,[]).append(edge)
    idx=_node_index(world)
    initial=_begin(world,traveller)
    # Include visited mask for one-time pickups and milestone mask. Time
    # period controls bus/ferry/airline transfers; min duration controls
    # intentionally circuitous routes. Quantized resource dominance bounds
    # state growth while allowing explicit fare/fuel/stamina constraints.
    def state_key(st):
        return (st.place,st.tokens,st.visits,st.requirements,
                st.clock%1440,st.money,st.energy,st.fuel,st.oxygen,st.mana,
                min(st.elapsed,minimum_minutes))
    best={state_key(initial):0}
    priority=[(0,0,initial)]
    counter=count(1)
    visited_states=0
    complete=(1<<len(requires))-1
    while priority and visited_states<expansion_cap:
        score,_,state=heappop(priority)
        if score!=best.get(state_key(state)):continue
        visited_states+=1
        if (state.place==world.goal and state.requirements==complete and
                state.elapsed>=minimum_minutes and state.route):
            return replay(world,state.route,traveller,objective=objective),visited_states,False
        for edge in outgoing.get(state.place,()):
            onward=_apply(world,traveller,state,edge,idx,requires)
            if onward is None:continue
            penalty=avoid.count(edge.id)
            increment=_cost(edge,onward.waiting_minutes-state.waiting_minutes,
                            objective,penalty)
            next_score=score+increment
            key=state_key(onward)
            if next_score>=best.get(key,float("inf")):continue
            best[key]=next_score
            heappush(priority,(next_score,next(counter),onward))
    return None,visited_states,bool(priority)

def replay(world:World,route:tuple[str,...],traveller:Traveller=Traveller(),*,
           objective:str="verified")->Journey:
    """Independently execute route choices; no arbitrary agent code."""
    validate_world(world);validate_traveller(traveller)
    if not isinstance(route,tuple) or not 1<=len(route)<=MAX_HOPS:
        raise ValueError("original route replay steps invalid")
    idx=_node_index(world)
    edges={item.id:item for item in world.connections}
    state=_begin(world,traveller)
    modes=[];shapes=[];secret=unlockable=environmental=0
    for action in route:
        if action not in edges:raise ValueError("route replay references missing edge")
        edge=edges[action]
        after=_apply(world,traveller,state,edge,idx,())
        if after is None:raise ValueError("route replay cannot traverse locked or unsafe segment")
        state=after
        modes.append(edge.mode);shapes.extend(edge.shapes)
        secret+=bool(edge.secret_token)
        unlockable+=bool(edge.requires or edge.requires_one)
        environmental+=bool(edge.weather_any or edge.weather_none or
                            edge.hazard_resistance)
    if state.place!=world.goal:
        raise ValueError("claimed original-world journey never reaches the goal")
    footprint=len(set(state.traversed_places))
    loops=len(state.traversed_places)-footprint
    canonical={
        "objective":objective,"edges":route,"places":state.traversed_places,
        "minutes":state.elapsed,"money":state.spent,"risk":state.danger,
        "energy":state.fatigue,
        "fuel":state.fuel_spent,"oxygen":state.oxygen_spent,
        "mana":state.mana_spent,"modes":modes,"shapes":sorted(set(shapes)),
        "weather":world.environment,
    }
    digest=sha256(json.dumps(canonical,sort_keys=True,separators=(",",":")
                             ).encode("utf-8")).hexdigest()
    return Journey(
        SCHEMA,objective,route,state.traversed_places,tuple(modes),
        tuple(sorted(set(shapes))),len(route),
        state.movement_minutes,state.waiting_minutes,state.elapsed,
        state.spent,state.danger,state.fatigue,state.spectacle,loops,
        footprint,secret,unlockable,environmental,True,True,digest,
        state.fuel_spent,state.oxygen_spent,state.mana_spent,
    )

def experience(world:World,traveller:Traveller=Traveller(), *,
               path:tuple[str,...]=())->dict:
    """Continue a genuinely playable original journey without requiring goal.

    A player can travel down a deadend, pick up a clue, turn around, take
    optional detours, wait for a train, or find an unlockable passage.
    Any undiscovered secret route is omitted from the choice menu rather
    than revealing its destination. Options are replayed on every request;
    the client never gets to mint cash, abilities or location.
    """
    validate_world(world);validate_traveller(traveller)
    if not isinstance(path,tuple) or len(path)>MAX_HOPS or any(
            type(item) is not str or not VALID_ID.fullmatch(item)
            for item in path):
        raise ValueError("world free-roam history exceeds bounded game actions")
    idx=_node_index(world)
    edges={item.id:item for item in world.connections}
    state=_begin(world,traveller)
    for action in path:
        if action not in edges:
            raise ValueError("free-roam journey includes nonexistent travel edge")
        after=_apply(world,traveller,state,edges[action],idx,())
        if after is None:
            raise ValueError("free-roam journey changed a locked, unsafe or unpaid route")
        state=after
    choices=[]
    if state.place!=world.goal:
        for edge in world.connections:
            if edge.origin!=state.place:continue
            # A secret passage unknown to this player does not leak its
            # identity or destination through API option counts.
            if edge.secret_token and edge.secret_token not in state.tokens:
                continue
            allowed=_apply(world,traveller,state,edge,idx,())
            reason="open"
            if allowed is None:
                if edge.weather_any and not set(world.environment).intersection(edge.weather_any):
                    reason="weather_restricted"
                elif edge.weather_none and set(world.environment).intersection(edge.weather_none):
                    reason="weather_restricted"
                elif state.money<edge.price:reason="fare_required"
                elif state.energy<edge.fatigue:reason="stamina_required"
                elif state.fuel<edge.fuel:reason="fuel_required"
                elif state.oxygen<edge.oxygen:reason="oxygen_required"
                elif state.mana<edge.mana:reason="magic_resource_required"
                elif state.elapsed+_depart(edge,state.clock)+edge.minutes>world.max_minutes:
                    reason="travel_time_exhausted"
                else:reason="progress_or_equipment_locked"
            choices.append({
                "edge":edge.id,"to":edge.destination,
                "mode":edge.mode,"family":MODES[edge.mode],
                "shape":list(edge.shapes),
                "time_minutes":edge.minutes,
                "waiting_minutes":_depart(edge,state.clock),
                "price":edge.price,"fatigue":edge.fatigue,
                "fuel":edge.fuel,"oxygen":edge.oxygen,"mana":edge.mana,
                "danger":edge.danger,"scenic":edge.spectacle,
                "access":reason,"available":allowed is not None,
            })
    return {
        "schema":SCHEMA,
        "world_position":state.place,
        "goal":world.goal,
        "completed":state.place==world.goal,
        "visited_places":list(state.traversed_places),
        "played_edges":list(path),
        "known_tokens":sorted(state.tokens),
        "remaining_cash":state.money,
        "remaining_energy":state.energy,
        "remaining_fuel":state.fuel,
        "remaining_oxygen":state.oxygen,
        "remaining_mana":state.mana,
        "elapsed_minutes":state.elapsed,
        "waiting_minutes":state.waiting_minutes,
        "clock_minute":state.clock%1440,
        "risk":state.danger,
        "scenic":state.spectacle,
        "options":choices,
        "scope":"original game-world traversal only; no real-world routing or licensed title content",
    }


def portfolio(world:World,traveller:Traveller=Traveller(),*,
              max_routes:int=12,expansion_cap:int=5000,
              include_circuitous:bool=True)->RouteSearch:
    validate_world(world);validate_traveller(traveller)
    _number(max_routes,1,24,"alternative journey count")
    _number(expansion_cap,100,MAX_EXPANSIONS,"search budget")
    if type(include_circuitous) is not bool:
        raise ValueError("long-route search control must be boolean")
    tasks=[(name,(),0) for name in OBJECTIVES]
    if include_circuitous:
        tasks.extend([
            ("exploratory",("shape:detour",),0),
            ("scenic",("shape:scenic",),0),
            ("balanced",("shape:shortcut",),0),
            ("safest",("shape:secret",),0),
            ("fastest",("shape:unlockable",),0),
            ("impractical",(),min(world.max_minutes,180)),
            ("exploratory",("shape:loop",),0),
            ("scenic",("shape:free_roam",),0),
        ])
    solutions=[]
    unique=set()
    examined=0
    truncated=False
    for objective,conditions,long_min in tasks:
        if len(solutions)>=max_routes:break
        avoid=tuple(dict.fromkeys(route.edges[0] for route in solutions if route.edges))
        found,count_states,limited=plan(
            world,traveller,objective=objective,requires=conditions,
            minimum_minutes=long_min,avoid=avoid[-10:],
            expansion_cap=expansion_cap,
        )
        examined+=count_states
        truncated|=limited
        if found is None or found.edges in unique:continue
        unique.add(found.edges)
        solutions.append(found)
    return RouteSearch(
        SCHEMA,world.start,world.goal,world.environment,
        "multisolver",tuple(solutions),examined,truncated,
        "bounded positive-cost Dijkstra across exact resource/visibility/weather state",
        "alternatives are executable abstract graph journeys, not proven exhaustive; "
        "specific vehicles, magic, spaceflight and water physics require separate adapters",
    )

def route_dictionary(result:RouteSearch)->dict:
    return asdict(result)

def verify_portfolio(world:World,traveller:Traveller,doc:dict)->dict:
    validate_world(world);validate_traveller(traveller)
    if not isinstance(doc,dict) or doc.get("schema")!=SCHEMA:
        raise ValueError("unrecognized original world journey document")
    entries=doc.get("routes")
    if not isinstance(entries,list) or not 1<=len(entries)<=24:
        raise ValueError("invalid bounded route evidence")
    found=set()
    for row in entries:
        if not isinstance(row,dict) or not isinstance(row.get("edges"),list):
            raise ValueError("route must contain exact edge sequence")
        journey=replay(world,tuple(row["edges"]),traveller,
                       objective=row.get("objective","verified"))
        if json.loads(json.dumps(asdict(journey)))!=row or journey.edges in found:
            raise ValueError("route portfolio gameplay metrics or diversity forged")
        found.add(journey.edges)
    if doc.get("start")!=world.start or doc.get("goal")!=world.goal or (
        doc.get("environment")!=list(world.environment)):
        raise ValueError("route portfolio attached to another world/weather")
    return {"schema":SCHEMA,"verified_routes":len(found),
            "claim":"replayed game-world route states, not physical vehicle simulation"}
