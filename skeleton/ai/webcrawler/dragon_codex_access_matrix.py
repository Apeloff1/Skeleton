"""Extended 128-gateway access matrix with conditional, delayed and lost paths.

Every source genome axis controls one distinguishable original gateway,
including seasonal, historical, technological, social and environmental
gates. Paths may be temporarily closed or intentionally never proved under
a bounded horizon. An endless game's validity does not depend on universal
reachability. The ordinary 16 constructive world gateways are still
available separately for users who want completion assurances.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from collections import deque

from .dragon_world_codex import (
    CodexAddress,DOMAINS,AXIS_NAMES,AXIS_INDEX,DOMAIN_INDEX,
    validate,
)
from .dragon_world_codex_runtime import (
    CodexState,start,step as world_step,
)
from .dragon_genomic_world import GenomicState
from .dragon_living_world import _sha,MAX_ABS_COORD

SCHEMA="skeleton.ai.dragon.delayed_access_matrix.v1"
MAX_PLAN_ACTIONS=96
ACCESS_TYPES=(
 "wild_shortcut","hydro_navigation","storm_corridor",
 "ecology_migration","settlement_transit","faction_passage",
 "market_ferry","technological_lift","dream_portal","orbital_shuttle",
 "historical_revelation","era_rift","turning_maze",
 "intermodal_transfer","secret_passage","postgame_expansion",
)
assert len(ACCESS_TYPES)==16

@dataclass(frozen=True)
class Gateway:
    id:str
    source_axis:str
    companion_axis:str
    source_domain:str
    route_type:str
    required_mastery:tuple[int,int]
    current_mastery:tuple[int,int]
    earliest_turn:int
    period:int
    season_window:int
    current_season:int
    required_era:int
    current_era:int
    time_window_open:bool
    mastery_earned:bool
    era_earned:bool
    season_open:bool
    accessible_now:bool
    next_possible_turn:int|None
    reason:str
    displacement:tuple[int,int]
    optional_path:bool
    mandatory_game_ending:bool


@dataclass(frozen=True)
class PassageState:
    world:CodexState
    traversed:tuple[str,...]=()
    discovered:tuple[str,...]=()
    access_digest:str=""


def create_passage_state(source:CodexAddress)->PassageState:
    world=start(source)
    return PassageState(
        world=world,
        access_digest=_sha([SCHEMA,source.codex_digest,"fresh_route_world"]),
    )


def _origin(source:CodexAddress,state:PassageState):
    root,genes=validate(source)
    if not isinstance(state,PassageState):
        raise ValueError("original access state missing")
    if (len(state.traversed)>MAX_PLAN_ACTIONS or
        any(v not in ("access_"+axis for axis in AXIS_NAMES)
            for v in state.traversed) or
        len(set(state.discovered))!=len(state.discovered)):
        raise ValueError("world passage travel receipt invalid")
    return root,genes


def _requirements(source:CodexAddress,state:PassageState,index:int,
                  *,search:bool=True)->Gateway:
    _,genes=_origin(source,state)
    if type(index) is not int or not 0<=index<128:
        raise ValueError("invalid access-gate coordinate")
    own=genes.values[index]
    paired_index=(index+3)%128
    other=genes.values[paired_index]
    skill=1+own//64
    companion=1+other//128
    first=3+own//12
    period=2+other%9
    # Calendar evolves every six source moves. Narrative and historical
    # periods may require several actual player turns, not an instant unlock.
    season=(state.world.player.base.turn//6)%4
    desired=(own//32)%4
    domain=DOMAINS[index//8]
    era_required=(1+own//128
                  if domain in ("chronology","postgame") else 0)
    turn=state.world.player.base.turn
    mastery=(state.world.axis_mastery[index],
             state.world.axis_mastery[paired_index])
    earned=(mastery[0]>=skill and mastery[1]>=companion)
    calendar=(turn>=first and turn%period==0)
    season_open=(season==desired)
    era_open=(state.world.era>=era_required)
    possible=earned and calendar and era_open and season_open
    # Do not conflate "not currently visible" with globally unreachable.
    next_turn=None
    if search:
        for upcoming in range(turn,min(turn+257,2**31-1)):
            if (upcoming>=first and upcoming%period==0 and
                    upcoming//6%4==desired):
                next_turn=upcoming
                break
    vector=(
        (index%7+1) * (-1 if (index//7)%2 else 1),
        (index%5+1) * (-1 if (index//5)%2 else 1),
    )
    route=ACCESS_TYPES[index//8]
    reason=("open" if possible else
            "era_change_required" if not era_open else
            "training_required" if not earned else
            "seasonal_window_closed" if not season_open else
            "temporal_window_closed")
    return Gateway(
        id="access_"+AXIS_NAMES[index],
        source_axis=AXIS_NAMES[index],
        companion_axis=AXIS_NAMES[paired_index],
        source_domain=domain,route_type=route,
        required_mastery=(skill,companion),
        current_mastery=mastery,
        earliest_turn=first,period=period,
        season_window=desired,current_season=season,
        required_era=era_required,current_era=state.world.era,
        time_window_open=calendar,
        mastery_earned=earned,
        era_earned=era_open,
        season_open=season_open,
        accessible_now=possible,
        next_possible_turn=next_turn,
        reason=reason,displacement=vector,
        optional_path=True,mandatory_game_ending=False,
    )


def inspect_gate(source:CodexAddress,state:PassageState,
                 gate_id:str)->Gateway:
    if type(gate_id) is not str or not gate_id.startswith("access_"):
        raise ValueError("original delayed access gate ID malformed")
    name=gate_id[7:]
    if name not in AXIS_INDEX:
        raise ValueError("delayed world gate has no physical world control")
    return _requirements(source,state,AXIS_INDEX[name])


def available_gates(source:CodexAddress,state:PassageState,
                    *,domain:str|None=None)->tuple[Gateway,...]:
    if domain is not None and domain not in DOMAIN_INDEX:
        raise ValueError("unknown world access domain")
    indices=(range(128) if domain is None else
             range(DOMAIN_INDEX[domain]*8,DOMAIN_INDEX[domain]*8+8))
    return tuple(_requirements(source,state,i) for i in indices)


def _hash_transition(source:CodexAddress,before:PassageState,
                     action:str,after:CodexState,
                     visited:tuple[str,...])->str:
    return _sha([SCHEMA,source.codex_digest,before.access_digest,
                 action,after.history_digest,
                 after.player.base.x,after.player.base.y,visited])


def take_access_action(source:CodexAddress,state:PassageState,
                       action:str)->PassageState:
    _origin(source,state)
    if type(action) is not str or len(action)>64 or (
        len(state.traversed)>=MAX_PLAN_ACTIONS):
        raise ValueError("original optional route action is out of bounds")
    if action in ("wait_world","rest_world") or (
        action.startswith("study_") and action[6:] in AXIS_INDEX):
        moved=world_step(source,state.world,action)
        visited=state.traversed
    elif action.startswith("access_"):
        gateway=inspect_gate(source,state,action)
        if not gateway.accessible_now:
            raise ValueError("secret/temporal/access route remains actually locked")
        # Time is consumed via the real world engine. Then the player's
        # position is changed and included in a chained materialized proof.
        moved=world_step(source,state.world,"wait_world")
        before=moved.player.base
        x=before.x+gateway.displacement[0]
        y=before.y+gateway.displacement[1]
        if abs(x)>MAX_ABS_COORD or abs(y)>MAX_ABS_COORD:
            raise ValueError("optional world route beyond playable game coordinates")
        new_base=replace(
            before,x=x,y=y,
            history_digest=_sha([
                before.history_digest,"original_optional_route",action,x,y,
            ]),
        )
        new_player=replace(
            moved.player,base=new_base,
            history_digest=_sha([
                moved.player.history_digest,action,x,y,
            ]),
        )
        moved=replace(
            moved,player=new_player,
            history_digest=_sha([
                moved.history_digest,action,new_player.history_digest,x,y,
            ]),
        )
        visited=state.traversed+(action,)
    else:
        raise ValueError("original optional world route transition does not exist")
    discovered=state.discovered
    if action.startswith("access_") and action not in discovered:
        discovered=discovered+(action,)
    return PassageState(
        world=moved,traversed=visited,discovered=discovered,
        access_digest=_hash_transition(source,state,action,moved,visited),
    )


def replay_access(source:CodexAddress,
                  actions:tuple[str,...])->PassageState:
    if (type(actions) is not tuple or len(actions)>MAX_PLAN_ACTIONS or
        any(type(action) is not str or len(action)>64 for action in actions)):
        raise ValueError("source world access history invalid or unbounded")
    state=create_passage_state(source)
    for action in actions:state=take_access_action(source,state,action)
    return state


def attempt_unlock(source:CodexAddress,gate_id:str, *,
                   horizon:int=96)->dict:
    """Construct a bounded route, reporting inconclusive when too distant.

    No implied universal winning condition. A gate with mutually
    incompatible seasonal/temporal constraints can remain unprovable
    even while the surrounding sandbox is valid and playable.
    """
    if type(horizon) is not int or not 8<=horizon<=MAX_PLAN_ACTIONS:
        raise ValueError("world access planning horizon outside source replay bound")
    state=create_passage_state(source)
    demands=inspect_gate(source,state,gate_id)
    script=[]
    if demands.required_era>0:
        for _ in range(demands.required_era*4):
            script.append("study_era_length")
    for name,have,need in zip(
        (demands.source_axis,demands.companion_axis),
        demands.current_mastery,demands.required_mastery,
    ):
        for _ in range(max(0,need-have)):
            script.append("study_"+name)
    if len(script)>=horizon:
        return {
            "schema":SCHEMA,"gate":gate_id,"found_within_budget":False,
            "actions":[],"reason":"preconditions_exceed_bounded_horizon",
            "not_a_global_unwinnability_claim":True,
        }
    for action in script:state=take_access_action(source,state,action)
    while len(script)<horizon-1:
        gate=inspect_gate(source,state,gate_id)
        if gate.accessible_now:
            script.append(gate_id)
            state=take_access_action(source,state,gate_id)
            independently=replay_access(source,tuple(script))
            if independently!=state:
                raise ValueError("world-access witness cannot replay the actual story")
            return {
                "schema":SCHEMA,"gate":gate_id,
                "found_within_budget":True,
                "actions":script,"elapsed_actions":len(script),
                "arrived":[state.world.player.base.realm,
                           state.world.player.base.x,
                           state.world.player.base.y],
                "actual_replay_digest":state.access_digest,
                "not_a_global_unwinnability_claim":True,
                "original_world_digest":source.codex_digest,
            }
        script.append("wait_world")
        state=take_access_action(source,state,"wait_world")
    return {
        "schema":SCHEMA,"gate":gate_id,"found_within_budget":False,
        "actions":[],"reason":"not_reachable_under_current_horizon_or_calendar",
        "not_a_global_unwinnability_claim":True,
    }
