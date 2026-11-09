"""Actual original game/quest journeys composed from independent mechanics.

World seeds never count as completed games. This plane assembles executable
player itineraries from a real rule program, replays all decisions and emits
content-addressed evidence for causally distinct outcomes.

16 gameplay strategies prioritize different aspects of one world (scenery,
economy, diplomacy, ecology, environment, weird secret loops, conquest,
postgame, etc.). Multiple paths can reach the same program destination or
different story outcomes; sandbox stories need never conclude.

Not a surrogate for human playtesting, fictional character/plot authoring,
asset production or 16 independently original games per generated index.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from hashlib import sha256
import json

from .dragon_original_mechanic_forge import (
    OriginalProgram,OriginalPlay,MECHANIC_COUNT,MECHANIC_IDS,
    RESOURCE_INDEX,initial,validate_program,perform,choices,
    replay,prove_mechanic,_digest,MAX_ACTIONS,
)

SCHEMA="skeleton.ai.dragon.original_campaign_forger.v1"
ROUTE_INTENTS=(
 "scenic_wander","direct_progress","long_impractical_detour",
 "safe_survival","resource_trader","settlement_architect",
 "realm_expedition","moving_maze_explorer","secret_key_seeker",
 "ecology_guardian","research_route","faction_negotiator",
 "alternate_conclusion","postgame_afterlife",
 "environment_challenge","cross_mechanic_synergy",
)
assert len(set(ROUTE_INTENTS))==16

ROUTE_WEIGHTS=(
 (8,0,7,6,14),(8,1,6,9,31),
 (8,7,6,9,0),(26,4,19,15,27),
 (20,12,11,21,17),(16,18,17,30,19),
 (10,13,2,1,12),(6,7,9,8,31),
 (9,7,24,23,10),(14,15,19,30,26),
 (28,29,10,31,24),(21,22,23,24,16),
 (24,23,22,25,31),(25,30,31,16,8),
 (2,3,4,5,27),(6,7,10,11,14),
)
assert len(ROUTE_WEIGHTS)==len(ROUTE_INTENTS)

@dataclass(frozen=True)
class GameJourney:
    schema:str
    source_digest:str
    design_index:str
    intent:str
    branch_seed:int
    requested_steps:int
    actions:tuple[str,...]
    visited_original_mechanics:tuple[str,...]
    actual_cross_mechanic_joins:tuple[str,...]
    actions_executed:int
    ending_variants:tuple[str,...]
    remains_playable:bool
    final_turn:int
    final_era:int
    final_realm:int
    final_location:tuple[int,int]
    actual_resource_changes:tuple[int,...]
    world_changes:tuple[str,...]
    final_history_digest:str
    trace_digest:str
    graph_guarantee:str


def _check(intent:int,branch_seed:int,steps:int):
    if type(intent) is not int or not 0<=intent<len(ROUTE_INTENTS):
        raise ValueError("original game experience route intent unsupported")
    if type(branch_seed) is not int or not 0<=branch_seed<2**32:
        raise ValueError("original game decision seed outside uint32 range")
    if type(steps) is not int or not 1<=steps<=MAX_ACTIONS:
        raise ValueError("original game route action horizon outside bounds")


def _choice(program:OriginalProgram,state:OriginalPlay,
            intent:int,branch_seed:int,index:int)->str:
    menu={item["id"]:item for item in choices(program,state)
          if item["available"]}
    eligible=[i for i,value in enumerate(program.intensities)
              if value>0 and "practice_"+MECHANIC_IDS[i] in menu]
    if not eligible:return "rest_world"
    if intent==15 and state.turn%4==3:
        joins=sorted(name for name in menu if name.startswith("join_"))
        if joins:return joins[(state.turn+branch_seed)%len(joins)]
    prefer=ROUTE_WEIGHTS[intent]
    if intent==2 and index%5<3:
        # Actually revisit the same scenic/doubleback zone many times:
        # impracticality is the decision pattern, not just a label.
        for i in (8,7,6):
            if i in eligible:return "practice_"+MECHANIC_IDS[i]
    # The designer can push this pathway toward its target original systems;
    # alternative seeds create different interleavings and resource outcomes.
    candidate=[
        i for i in prefer if i in eligible
    ]
    candidate+=sorted(i for i in eligible if i not in candidate)
    if index%11==10 and "rest_world" in menu:
        return "rest_world"
    position=(index*(1+intent%3)+branch_seed%(len(candidate)))%len(candidate)
    return "practice_"+MECHANIC_IDS[candidate[position]]


def compose_journey(
    program:OriginalProgram,*,route_intent:int,
    branch_seed:int=0,steps:int=32,
)->GameJourney:
    validate_program(program)
    _check(route_intent,branch_seed,steps)
    here=initial(program)
    baseline=here
    actions=[]
    real_names=[]
    for index in range(steps):
        action=_choice(program,here,route_intent,branch_seed,index)
        if action not in {item["id"] for item in choices(program,here)
                          if item["available"]}:
            raise ValueError("original route composer chose a fictional or locked passage")
        new=perform(program,here,action)
        if new.history_digest==here.history_digest:
            raise ValueError("original journey emitted unperformed action")
        actions.append(action)
        if action.startswith("practice_"):
            real_names.append(action.removeprefix("practice_"))
        here=new
    if here!=replay(program,tuple(actions)):
        raise ValueError("composed original campaign differs from actual independent replay")
    return GameJourney(
        schema=SCHEMA,source_digest=program.source_digest,
        design_index=program.decimal_index,
        intent=ROUTE_INTENTS[route_intent],branch_seed=branch_seed,
        requested_steps=steps,actions=tuple(actions),
        visited_original_mechanics=tuple(sorted(set(real_names))),
        actual_cross_mechanic_joins=here.unlocked_joins,
        actions_executed=here.turn,
        ending_variants=here.endings,
        remains_playable=True,
        final_turn=here.turn,final_era=here.era,
        final_realm=here.realm,final_location=(here.x,here.y),
        actual_resource_changes=tuple(
            a-b for a,b in zip(here.resources,baseline.resources)),
        world_changes=here.changed_places,
        final_history_digest=here.history_digest,
        trace_digest=_digest([
            SCHEMA,program.source_digest,route_intent,
            branch_seed,actions,here.history_digest,
        ]),
        graph_guarantee="valid replayed bounded player journey, "
                        "no mandatory winning condition or arbitrary future safety claim",
    )


def verify_journey(program:OriginalProgram,journey:GameJourney)->dict:
    validate_program(program)
    if not isinstance(journey,GameJourney) or journey.schema!=SCHEMA or (
        journey.source_digest!=program.source_digest or
        journey.design_index!=program.decimal_index or
        journey.intent not in ROUTE_INTENTS
    ):
        raise ValueError("original journey detached from its real authored world")
    expected=compose_journey(
        program,route_intent=ROUTE_INTENTS.index(journey.intent),
        branch_seed=journey.branch_seed,steps=journey.requested_steps,
    )
    if expected!=journey:
        raise ValueError("original mechanics game journey actions or world changes forged")
    return {
        "schema":SCHEMA,"verified":True,"actual_steps":len(journey.actions),
        "experienced_ending_count":len(journey.ending_variants),
        "cross_mechanic_routes":len(journey.actual_cross_mechanic_joins),
        "physical_game_journey":True,
        "claim":"independently recomputed original mechanics, not a shipped game",
    }


def sample_experiences(program:OriginalProgram, *,
                       seed:int=0,limit:int=16,steps:int=24)->dict:
    validate_program(program)
    if type(limit) is not int or not 1<=limit<=16:
        raise ValueError("route sampling must be 1..16 actual experiences")
    _check(0,seed,steps)
    games=[compose_journey(
        program,route_intent=i,branch_seed=seed,steps=steps,
    ) for i in range(limit)]
    unique={x.actions for x in games}
    worlds={x.final_history_digest for x in games}
    return {
        "schema":SCHEMA,"source_digest":program.source_digest,
        "sampled":len(games),
        "distinct_observed_action_sequences":len(unique),
        "different_measured_final_stories":len(worlds),
        "programs_materialized_as_finished_games":0,
        "experiences":[asdict(x) for x in games],
        "claim":"actual game outcomes for THIS bounded sample only; "
                "no global uniqueness or enjoyment assumption",
    }


def demonstrate_mechanics(program:OriginalProgram)->dict:
    validate_program(program)
    examples=[prove_mechanic(program,i) for i in range(MECHANIC_COUNT)]
    return {
        "schema":SCHEMA,"source_digest":program.source_digest,
        "available_original_mechanics":sum(x["available"] for x in examples),
        "mechanic_execution_witnesses":examples,
        "claimed_distinctness":"each active level has concrete causal gameplay evidence",
    }
