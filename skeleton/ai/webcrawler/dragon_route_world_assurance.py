"""Original-world route assurance: meaningful choices, softlock indicators and rewards.

Quality diagnostics are structural and replay-driven. They do not claim that
every possible resource depletion/path/weather combination is solvable or
that a given player enjoys backtracking. The design gate rejects unreachable
regions and dead ends with neither a reward nor an escape.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from collections import deque

from .dragon_route_world import World,Traveller,validate_world,plan,experience
from .dragon_route_taxonomy import MODES

SCHEMA="skeleton.ai.dragon.original_route_assurance.v1"

@dataclass(frozen=True)
class RouteWorldQuality:
    schema:str
    places:int
    transitions:int
    topology_reachable:int
    topology_goal_recoverable:int
    unreachable_places:tuple[str,...]
    no_topological_goal_escape:tuple[str,...]
    structural_dead_ends:tuple[str,...]
    unrewarded_dead_ends:tuple[str,...]
    loops:int
    real_public_transport_modes:tuple[str,...]
    real_environmental_modes:tuple[str,...]
    fictional_and_space_modes:tuple[str,...]
    hidden_secrets_initially:tuple[str,...]
    initial_visible_secrets:tuple[str,...]
    unlocked_or_secret_connections:int
    weather_restricted_connections:int
    paid_connections:int
    timetabled_connections:int
    fully_executable_original_goal_route:bool
    stress_warnings:tuple[str,...]
    certification:str


def _reach(start:str,adj:dict[str,set[str]])->set[str]:
    todo=deque([start]);seen=set()
    while todo:
        current=todo.popleft()
        if current in seen:continue
        seen.add(current)
        todo.extend(sorted(adj[current]-seen))
    return seen

def audit_world(world:World,traveller:Traveller=Traveller(), *,
                max_search:int=3500)->RouteWorldQuality:
    validate_world(world)
    if type(max_search) is not int or not 100<=max_search<=10000:
        raise ValueError("original world audit must have a bounded solver budget")
    places={site.id:site for site in world.places}
    outgoing={name:set() for name in places}
    incoming={name:set() for name in places}
    for route in world.connections:
        outgoing[route.origin].add(route.destination)
        incoming[route.destination].add(route.origin)
    from_start=_reach(world.start,outgoing)
    towards_goal=_reach(world.goal,incoming)
    unreached=tuple(sorted(set(places)-from_start))
    dead_goals=tuple(sorted(set(places)-towards_goal))
    dead_ends=[]
    empty_rewards=[]
    for site in world.places:
        if site.id in (world.start,world.goal):continue
        if outgoing[site.id] and outgoing[site.id]<=incoming[site.id]:
            dead_ends.append(site.id)
            if not (site.gifts or site.scenic_value>=25 or
                    site.energy_refill or site.money_pickup):
                empty_rewards.append(site.id)
    loop_edges=sum(route.origin in _reach(route.destination,outgoing)
                   for route in world.connections)
    visible=experience(world,traveller)["options"]
    disclosed={option["edge"] for option in visible}
    hidden=tuple(sorted(
        item.id for item in world.connections if item.secret_token))
    initial_visible=tuple(sorted(x for x in hidden if x in disclosed))
    families={MODE for MODE in MODES.values()}
    buckets={group:set() for group in families}
    for edge in world.connections:buckets[MODES[edge.mode]].add(edge.mode)
    attempted,seen,truncated=plan(world,traveller,objective="fastest",
                                 expansion_cap=max_search)
    issues=[]
    if unreached:issues.append("unreachable_original_locations")
    if dead_goals:issues.append("regions_without_a_reverse_goal_escape")
    if empty_rewards:issues.append("unrewarded_detour_deadends")
    if initial_visible:issues.append("undiscovered_secret_route_leak")
    if not attempted:issues.append("no_proven_winning_journey_with_current_resources")
    if truncated:issues.append("bounded_route_solver_cut_short")
    if loop_edges==0:issues.append("no_true_world_free_roam_cycle")
    if sum(bool(e.requires or e.secret_token) for e in world.connections)==0:
        issues.append("no_unlockable_world_progression")
    return RouteWorldQuality(
        schema=SCHEMA,places=len(world.places),
        transitions=len(world.connections),topology_reachable=len(from_start),
        topology_goal_recoverable=len(towards_goal),
        unreachable_places=unreached,no_topological_goal_escape=dead_goals,
        structural_dead_ends=tuple(sorted(dead_ends)),
        unrewarded_dead_ends=tuple(sorted(empty_rewards)),loops=loop_edges,
        real_public_transport_modes=tuple(sorted(buckets.get("wheeled",set()))),
        real_environmental_modes=tuple(sorted(buckets.get("environment",set()))),
        fictional_and_space_modes=tuple(sorted(
            buckets.get("fictional",set())|buckets.get("space",set()))),
        hidden_secrets_initially=hidden,
        initial_visible_secrets=initial_visible,
        unlocked_or_secret_connections=sum(bool(e.requires or e.secret_token)
                                            for e in world.connections),
        weather_restricted_connections=sum(bool(e.weather_any or e.weather_none)
                                           for e in world.connections),
        paid_connections=sum(e.price>0 for e in world.connections),
        timetabled_connections=sum(bool(e.departures) for e in world.connections),
        fully_executable_original_goal_route=attempted is not None,
        stress_warnings=tuple(issues),
        certification="bounded abstract graph and one executable route; resource "
            "softlocks, player satisfaction and specific vehicle physics not certified",
    )

def demand_viable_world(world:World,traveller:Traveller=Traveller())->dict:
    result=audit_world(world,traveller)
    if (result.unreachable_places or result.no_topological_goal_escape or
            result.unrewarded_dead_ends or result.initial_visible_secrets or
            not result.fully_executable_original_goal_route or
            result.loops==0):
        raise ValueError("original world fails route accessibility or progression gate")
    return asdict(result)


def climate_suite(*,seed:int=1,hour:int=8)->dict:
    from .dragon_route_world_factory import make_frontier,scenario_digest
    variants=[]
    for weather in ("clear","rain","windy","storm","snow","high_tide"):
        world,visitor=make_frontier(seed=seed,weather=weather,hour=hour)
        result=audit_world(world,visitor,max_search=3000)
        variants.append({
            "weather":weather,"world_sha256":scenario_digest(world),
            "goal_reached":result.fully_executable_original_goal_route,
            "unreachable":list(result.unreachable_places),
            "no_escape":list(result.no_topological_goal_escape),
            "warnings":list(result.stress_warnings),
            "route_count":result.transitions,
        })
    return {
        "schema":SCHEMA,
        "scenarios":variants,
        "all_six_weather_states_reach_goal":all(x["goal_reached"] for x in variants),
        "claim":"weather-tested original abstract travel, no detailed meteorological physics",
    }
