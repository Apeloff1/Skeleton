"""Lazily materialize **actual playable** indexed original world alternatives.

Every requested (world ID, variation, route slot) yields its own simulated
choice history, resources, consequences and exact replay receipt. The
16,000,000 addresses are *possible on-demand original route variants*:
they are not claimed to be completed titles, subjectively unique adventures
or 16m already certified paths. Route objectives are conditional on the
selected game world's real rules; an endless sandbox is allowed to return
a meaningful non-winning itinerary.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
from hashlib import sha256
import json

from .dragon_living_world import (
    LivingWorld,LivingState,SCHEMA as WORLD_SCHEMA,STYLE_NAMES,DIRS,
    initial_state,take_action,options,replay,describe,validate_world,
    _stable_number,_sha,VARIANTS_PER_ADDRESS,WORLD_ADDRESS_COUNT,
)
SCHEMA="skeleton.ai.dragon.living_world_alternative.v1"
POLICIES=(
    "cartographer",
    "survivalist",
    "settlement_builder",
    "scientific_explorer",
    "social_reconciler",
    "mercantile_route",
    "wilderness_champion",
    "civic_champion",
    "boundary_breaker",
    "wanderer",
)
assert len(POLICIES)==VARIANTS_PER_ADDRESS

RECIPES={
    "cartographer":("observe","north","east","survey","south","west"),
    "survivalist":("forage","forage","rest","farm","forage","wait"),
    "settlement_builder":("forage","forage","build","mine","craft","terraform"),
    "scientific_explorer":("survey","survey","mine","craft","research",
                           "ending_knowledge_keeper"),
    "social_reconciler":("help_settlers","help_settlers","negotiate",
                          "help_wilds","help_wilds","ending_restored_world"),
    "mercantile_route":("mine","trade","mine","trade","mine","trade",
                        "ending_merchant_compact"),
    "wilderness_champion":("help_wilds","help_wilds",
                            "ending_wilderness_guardian"),
    "civic_champion":("help_settlers","help_settlers","ending_civic_union"),
    "boundary_breaker":("observe","portal_1","survey","ride_shuttle",
                        "take_ferry","ending_starfarer"),
    "wanderer":("observe","east","north","west","south","observe","rest"),
}

@dataclass(frozen=True)
class IndexedRoute:
    schema:str
    world_id:int
    variant:int
    slot:int
    sample_budget:int
    objective:str
    world_fingerprint:str
    actions:tuple[str,...]
    endpoints:tuple[tuple[int,int,int],...]
    chapters_seen:int
    realms_visited:tuple[int,...]
    original_endings:tuple[str,...]
    ending_is_required:bool
    completed_world:bool
    remains_playable:bool
    persistent_changes:tuple[str,...]
    starting_replay_digest:str
    ending_replay_digest:str
    trace_digest:str
    claim:str


def _actual_available(world:LivingWorld,state:LivingState)->dict:
    return {item["name"]:item for item in options(world,state)
            if item["available"]}

def _wander(world:LivingWorld,state:LivingState,slot:int)->str:
    available=_actual_available(world,state)
    orientations=[
        "north","east","south","west",
    ]
    first=_stable_number(world.seed,slot,state.turn,"compass")%4
    for offset in range(4):
        name=orientations[(first+offset)%4]
        if name in available:
            return name
    # A changing maze always supports some route, but a depleted-energy
    # survivor may need a genuine rest before traversing it.
    return "rest" if "rest" in available else "wait"


def _choose(world:LivingWorld,state:LivingState,slot:int,step:int)->str:
    policy=POLICIES[slot]
    actions=_actual_available(world,state)
    preferred=RECIPES[policy]
    if step<len(preferred) and preferred[step] in actions:
        return preferred[step]
    # Work within game-style capability boundaries rather than offering
    # a research action to a world with no science/discovery mechanics.
    if policy=="survivalist":
        return "forage" if step%3!=1 else "rest"
    if policy in ("settlement_builder","mercantile_route"):
        for option in ("build","mine","farm","trade","craft","forage"):
            if option in actions and (
                option not in ("build","farm","craft") or
                step%3==0):
                return option
    if policy in ("civic_champion","social_reconciler") and (
        "help_settlers" in actions and step%4!=3):
        return "help_settlers"
    if policy=="wilderness_champion" and "help_wilds" in actions:
        return "help_wilds"
    if policy=="scientific_explorer":
        for option in ("survey","research","mine","observe"):
            if option in actions:return option
    if policy=="boundary_breaker":
        targets=sorted(x for x in actions if x.startswith("portal_"))
        if targets and step%4==1:
            return targets[(step//4)%len(targets)]
        for mode in ("take_ferry","ride_shuttle"):
            if mode in actions:return mode
    if policy=="cartographer" and step%3==0 and "observe" in actions:
        return "observe"
    return _wander(world,state,slot)


def materialize_route(world:LivingWorld,slot:int,*,steps:int|None=None)->IndexedRoute:
    validate_world(world)
    if type(slot) is not int or not 0<=slot<len(POLICIES):
        raise ValueError("original living-world route slot must be 0..9")
    if steps is None:steps=12+slot
    if type(steps) is not int or not 4<=steps<=48:
        raise ValueError("original route path sampling must use 4..48 decisions")
    state=initial_state(world)
    prior=state.history_digest
    actions=[]
    coords=[(state.realm,state.x,state.y)]
    for step in range(steps):
        choices=_actual_available(world,state)
        if not choices:
            break
        action=_choose(world,state,slot,step)
        if action not in choices:
            action="rest" if "rest" in choices else "restart_run"
        if action not in choices:
            raise ValueError("playable world offered no valid bounded step")
        state=take_action(world,state,action)
        actions.append(action)
        coords.append((state.realm,state.x,state.y))
        if not state.alive or (
            state.endings_seen and not world.allows_continuation
        ):
            break
    completed=bool(state.endings_seen)
    continued=describe(world,state,include_options=False)["playable"]
    return IndexedRoute(
        schema=SCHEMA,world_id=world.world_id,variant=world.variant,
        slot=slot,sample_budget=steps,objective=POLICIES[slot],
        world_fingerprint=world.world_fingerprint,
        actions=tuple(actions),endpoints=tuple(coords),
        chapters_seen=state.chapter,
        realms_visited=tuple(sorted({x[0] for x in coords})),
        original_endings=state.endings_seen,
        ending_is_required=world.lifecycle=="mandatory_completion",
        completed_world=completed,
        remains_playable=continued,
        persistent_changes=state.world_changes,
        starting_replay_digest=prior,
        ending_replay_digest=state.history_digest,
        trace_digest=_sha([
            world.world_fingerprint,slot,actions,coords,
            state.history_digest,
        ]),
        claim="each requested original route physically replayed; no claim of "
              "subjective uniqueness, legal clearance, finished game or optimality",
    )


def verify_route(world:LivingWorld,route:IndexedRoute)->dict:
    if not isinstance(route,IndexedRoute) or route.schema!=SCHEMA or (
        route.world_fingerprint!=world.world_fingerprint or
        route.world_id!=world.world_id or route.variant!=world.variant
    ):
        raise ValueError("original route variant evidence belongs to another game world")
    expected=materialize_route(world,route.slot,steps=route.sample_budget)
    # Exact recomputation catches mutated actions/outcomes/coordinates,
    # including fake claiming an ending for an endless playable game.
    if expected!=route or replay(world,route.actions).history_digest!=route.ending_replay_digest:
        raise ValueError("original world alternative was modified or not actually played")
    return {
        "schema":SCHEMA,"verified":True,
        "steps":len(route.actions),"ending":list(route.original_endings),
        "world_still_playable":route.remains_playable,
    }


def portfolio(world:LivingWorld,*,limit:int=10)->dict:
    validate_world(world)
    if type(limit) is not int or not 1<=limit<=10:
        raise ValueError("original world alternative portfolio bound is 1..10")
    entries=[materialize_route(world,index) for index in range(limit)]
    signatures=set()
    for entry in entries:
        # Detect accidental identical decisions. In that case be truthful
        # about diversity; slots remain materializable independently.
        signatures.add(entry.actions)
    return {
        "schema":SCHEMA,"world_fingerprint":world.world_fingerprint,
        "addressable_route_slot_count":VARIANTS_PER_ADDRESS,
        "sampled":len(entries),"distinct_replayed_action_sequences":len(signatures),
        "world_has_ending":world.includes_goal,
        "samples":[asdict(x) for x in entries],
        "claim":"sampled actual mutable-world play histories; untested address space not certified",
    }


def indexed_route(world_id:int,variation:int,slot:int,*,style:str|None=None)->IndexedRoute:
    from .dragon_living_world import create_world
    return materialize_route(
        create_world(world_id=world_id,variant=variation,style=style),slot)
