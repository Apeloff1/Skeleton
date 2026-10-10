"""Executable 128-axis world codex and earned delayed traversal.

Every axis has a distinct actual action, domain effect and evolving tile
projection. Temporal gates depend on achieved progress, environmental phase,
world history and explicit wait; not all worlds need a mandatory ending.
This source models turn-based rules and platform-neutral gameplay, not a
claim of implemented 3D physics or hardware release.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass,replace
from hashlib import sha256

from .dragon_world_codex import (
    CodexAddress,WorldCodex,DOMAIN_AXIS,DOMAINS,AXIS_NAMES,
    AXIS_INDEX,DOMAIN_INDEX,validate,
)
from .dragon_genomic_world import (
    GenomicState,initial_genomic_state,play as genomic_play,
    report as genomic_report,cell as genomic_cell,
)
from .dragon_genomic_paths import CHOICE_VERBS
from .dragon_living_world import MAX_ABS_COORD,_sha

SCHEMA="skeleton.ai.dragon.codex_world_runtime.v1"
MAX_SEQUENCES=96
MAX_INTENSITY=100000
GATE_MODES=(
 "traverse_cavern_depths","ride_tidal_corridor",
 "cross_storm_front","follow_migration_route",
 "rebuild_city_bridge","cross_diplomatic_border",
 "travel_merchant_corridor","activate_research_lift",
 "enter_dream_passage","transfer_orbital_lane",
 "follow_story_revelation","reach_past_era",
 "navigate_rotating_maze","take_multimodal_express",
 "unlock_secret_traverse","explore_postgame_frontier",
)
GATE_VECTORS=(
 (-2,-3),(4,1),(3,-2),(-3,2),(4,0),(-2,2),
 (6,0),(0,-5),(3,3),(7,-1),(1,4),(-4,-1),
 (-1,5),(5,1),(4,4),(-5,2),
)
assert len(GATE_MODES)==len(DOMAINS)==len(GATE_VECTORS)
GATE_TO_DOMAIN=dict(zip(GATE_MODES,DOMAINS))


@dataclass(frozen=True)
class CodexState:
    player:GenomicState
    axis_mastery:tuple[int,...]=(0,)*128
    domain_reputation:tuple[int,...]=(0,)*16
    opened_gates:tuple[str,...]=()
    journeys:tuple[str,...]=()
    era:int=0
    world_pressure:int=0
    history_digest:str=""
    actions:int=0


def start(address:CodexAddress)->CodexState:
    root,codex=validate(address)
    gen=initial_genomic_state(root)
    return CodexState(
        player=gen,
        domain_reputation=tuple(codex.values[n*8]//16 for n in range(16)),
        world_pressure=codex.level("hostile_pressure")//16 if (
            "hostile_pressure" in AXIS_INDEX) else codex.level("predator_pressure")//16,
        history_digest=_sha([SCHEMA,address.codex_digest,"initial_gameplay"]),
    )


def _valid(address:CodexAddress,state:CodexState):
    if not isinstance(state,CodexState):
        raise ValueError("original world codex game state is required")
    root,codex=validate(address)
    if (type(state.axis_mastery) is not tuple or len(state.axis_mastery)!=128
        or type(state.domain_reputation) is not tuple or
        len(state.domain_reputation)!=16 or
        any(type(x) is not int or not 0<=x<=MAX_INTENSITY
            for x in state.axis_mastery+state.domain_reputation)
        or type(state.era) is not int or not 0<=state.era<2**31
        or type(state.world_pressure) is not int or
        not 0<=state.world_pressure<=MAX_INTENSITY
        or type(state.actions) is not int or not 0<=state.actions<2**31
        or any(type(k) is not str or k not in GATE_MODES
               for k in state.opened_gates)
        or len(set(state.opened_gates))!=len(state.opened_gates)
        or any(type(k) is not str or k not in GATE_MODES for k in state.journeys)
        or len(state.journeys)>64
        or type(state.history_digest) is not str or
        len(state.history_digest)!=64):
        raise ValueError("invalid or forged original world environmental state")
    return root,codex


def _gate(address:CodexAddress,state:CodexState,index:int)->dict:
    root,codex=_valid(address,state)
    domain=DOMAINS[index]
    axis0=index*8
    axis1=axis0+1
    intensity=codex.values[axis0]
    secondary=codex.values[axis1]
    # A delayed destination has *two actual authored prerequisites* and
    # its own time-window clock. Players may choose to wait for the window.
    needed0=1+intensity//64
    needed1=1+secondary//64
    turn=state.player.base.turn
    earliest=2+intensity//16
    period=2+secondary%7
    first=max(turn,earliest)
    available_turn=first+(-first)%period
    earned=(state.axis_mastery[axis0]>=needed0 and
            state.axis_mastery[axis1]>=needed1)
    domain_score=state.domain_reputation[index]
    danger=max(0,secondary//48-domain_score//12)
    resource_cost=1+secondary//80
    currently=earned and turn>=earliest and turn%period==0
    mode=GATE_MODES[index]
    return {
        "name":mode,"domain":domain,"axis_required":[
            AXIS_NAMES[axis0],AXIS_NAMES[axis1]],
        "mastery_required":[needed0,needed1],
        "mastery_current":[state.axis_mastery[axis0],
                           state.axis_mastery[axis1]],
        "earned":earned,"available":currently,
        "earliest_turn":earliest,
        "cycle_period":period,
        "next_window_turn":available_turn,
        "reason":("open" if currently else
                  "mastery_locked" if not earned else
                  "future_epoch_locked" if turn<earliest else
                  "wait_for_window"),
        "danger":danger,"travel_cost":resource_cost,
        "moves_to":list(GATE_VECTORS[index]),
        "already_discovered":mode in state.opened_gates,
        "requirements_are_playable":True,
    }


def gate_catalog(address:CodexAddress,state:CodexState)->list[dict]:
    return [_gate(address,state,i) for i in range(16)]


def available_actions(address:CodexAddress,state:CodexState)->list[dict]:
    root,codex=_valid(address,state)
    result=[{
        "name":"wait_world","available":True,
        "reason":"open","kind":"advance_world_time",
    },{
        "name":"rest_world","available":True,
        "reason":"open","kind":"recover_player",
    }]
    for i,axis in enumerate(AXIS_NAMES):
        domain=DOMAINS[i//8]
        level=codex.values[i]
        result.append({
            "name":"study_"+axis,"available":True,
            "domain":domain,"axis":axis,"level":level,
            "strength":1+level//16,
            "current_mastery":state.axis_mastery[i],
            "kind":"real_domain_progress_and_game_state_change",
        })
    for gate in gate_catalog(address,state):
        result.append({
            "name":gate["name"],"available":gate["available"],
            "reason":gate["reason"],"kind":"earned_delayed_traversal",
            "next_window_turn":gate["next_window_turn"],
            "mastery_current":gate["mastery_current"],
            "mastery_required":gate["mastery_required"],
        })
    return result


def codex_cell(address:CodexAddress,state:CodexState,
               x:int|None=None,y:int|None=None)->dict:
    root,codex=_valid(address,state)
    hero=state.player.base
    col=hero.x if x is None else x
    row=hero.y if y is None else y
    base=genomic_cell(root,state.player,hero.realm,col,row)
    tick=hero.turn
    domains={}
    for i,name in enumerate(DOMAINS):
        levels=codex.domain(name)
        # All eight domain axes affect the cell's actual simulated field.
        # Time and coordinate alter the resulting field deterministically.
        signal=_sha([address.codex_digest,name,col//4,row//4,tick//6])
        local_noise=int(signal[:8],16)%32
        mean=sum(levels)//8
        domains[name]={
            "energy":mean+local_noise,
            "instability":(levels[0]+levels[3]+levels[6]+tick)%256,
            "resource_supply":max(0,levels[2]+levels[5]-
                                   levels[4]//2),
            "clock":tick//(1+levels[1]%24),
            "hazard":(levels[1]+levels[4]+local_noise)//8,
            "discovered_mastery":sum(state.axis_mastery[i*8:i*8+8]),
            "terrain_signature":signal[:16],
        }
    base.update({
        "codex_terrain":domains,
        "codex_source_digest":address.codex_digest,
        "codex_cell_digest":_sha([
            address.codex_digest,col,row,tick,domains,
        ]),
        "era":state.era,
        "original_world_only":True,
        "gameplay_claim":"128 original configuration axes are used in "
                         "terrain projection and playable progression",
    })
    return base


def step(address:CodexAddress,state:CodexState,action:str)->CodexState:
    root,codex=_valid(address,state)
    if type(action) is not str or len(action)>64:
        raise ValueError("original world transition action malformed")
    if state.actions>=2**31-2:
        raise ValueError("original world history counter exhausted")
    player=state.player
    new_mastery=list(state.axis_mastery)
    new_rep=list(state.domain_reputation)
    opened=list(state.opened_gates)
    journeys=list(state.journeys)
    pressure=state.world_pressure
    era=state.era
    if action=="wait_world":
        player=genomic_play(root,player,"wait")
    elif action=="rest_world":
        player=genomic_play(root,player,"rest")
    elif action.startswith("study_"):
        axis=action.removeprefix("study_")
        if axis not in AXIS_INDEX:
            raise ValueError("original study action has no implemented physical axis")
        i=AXIS_INDEX[axis]
        # All study actions are available to any *playable* original world
        # regardless of mandatory story completion. The underlying world
        # retains normal end-state restrictions.
        verbs=CHOICE_VERBS
        player=genomic_play(root,player,verbs[i%len(verbs)])
        level=codex.values[i]
        earned=1+level//16
        new_mastery[i]=min(MAX_INTENSITY,new_mastery[i]+1)
        new_rep[i//8]=min(MAX_INTENSITY,new_rep[i//8]+earned)
        pressure=min(MAX_INTENSITY,pressure+level//80)
        # Narrative and historical domains literally alter epoch progression
        # without fabricating a mandatory ending.
        if DOMAINS[i//8] in ("chronology","postgame") and (
                new_mastery[i]%4==0):
            era+=1
    elif action in GATE_TO_DOMAIN:
        index=DOMAIN_INDEX[GATE_TO_DOMAIN[action]]
        gate=_gate(address,state,index)
        if not gate["available"]:
            raise ValueError("real world passage is locked by progress or time")
        # The room/realm transition executes only after all prerequisites.
        # A reader can choose to unlock, skip, revisit, doubleback, or wait.
        player=genomic_play(root,player,"observe")
        delta=GATE_VECTORS[index]
        old=player.base
        target=(old.x+delta[0],old.y+delta[1])
        if any(abs(n)>MAX_ABS_COORD for n in target):
            raise ValueError("authored destination beyond valid original world")
        player=replace(player,base=replace(
            old,x=target[0],y=target[1],
            history_digest=_sha([
                old.history_digest,"codex_delayed_route",
                address.codex_digest,action,target,old.turn,
            ]),
        ))
        if action not in opened:opened.append(action)
        journeys=(journeys+[action])[-64:]
        new_rep[index]=min(MAX_INTENSITY,new_rep[index]+2)
        pressure=min(MAX_INTENSITY,pressure+gate["danger"])
        if GATE_TO_DOMAIN[action] in ("chronology","cosmology","postgame"):
            era+=1
    else:
        raise ValueError("original world action not available")
    evolved=replace(
        state,player=player,axis_mastery=tuple(new_mastery),
        domain_reputation=tuple(new_rep),
        opened_gates=tuple(opened),journeys=tuple(journeys),
        world_pressure=pressure,era=era,actions=state.actions+1,
        history_digest=_sha([
            SCHEMA,address.codex_digest,state.history_digest,
            action,player.history_digest,
            new_mastery,new_rep,opened,journeys,pressure,era,
        ]),
    )
    _valid(address,evolved)
    return evolved


def replay(address:CodexAddress,actions:tuple[str,...]=())->CodexState:
    if (type(actions) is not tuple or len(actions)>MAX_SEQUENCES or
            any(type(a) is not str or len(a)>64 for a in actions)):
        raise ValueError("original codex world action replay bounded to 96 steps")
    current=start(address)
    for action in actions:current=step(address,current,action)
    return current


def witness_to_gate(address:CodexAddress,domain:str,
                    *,starting_state:CodexState|None=None)->tuple[str,...]:
    if domain not in DOMAIN_INDEX:
        raise ValueError("only actual original world domains can be unlocked")
    current=start(address) if starting_state is None else starting_state
    pos=DOMAIN_INDEX[domain]
    plan=[]
    gate=_gate(address,current,pos)
    for axis,required,actual in zip(
        gate["axis_required"],gate["mastery_required"],
        gate["mastery_current"],
    ):
        for _ in range(max(0,required-actual)):
            command="study_"+axis
            current=step(address,current,command)
            plan.append(command)
    # Time access is procedural and finite, not a teleport around locks.
    for _ in range(42):
        gate=_gate(address,current,pos)
        if gate["available"]:break
        current=step(address,current,"wait_world")
        plan.append("wait_world")
    else:
        raise ValueError("temporal gate lacks any constructive unlock")
    plan.append(gate["name"])
    arrived=step(address,current,gate["name"])
    if gate["name"] not in arrived.opened_gates:
        raise ValueError("constructed unlock never actually traversed")
    return tuple(plan)


def proof_of_access(address:CodexAddress,domain:str)->dict:
    itinerary=witness_to_gate(address,domain)
    again=replay(address,itinerary)
    gate=GATE_MODES[DOMAIN_INDEX[domain]]
    if gate not in again.opened_gates:
        raise ValueError("original corridor evidence failed to reach destination")
    return {
        "schema":SCHEMA,
        "domain":domain,"route":gate,
        "actual_commands":list(itinerary),
        "steps":len(itinerary),
        "completed_non_mandatory_passage":True,
        "world_is_not_required_to_have_an_ending":True,
        "actual_destination":[again.player.base.realm,
                              again.player.base.x,again.player.base.y],
        "end_source_digest":again.history_digest,
        "source_genome":address.codex_digest,
    }


def report(address:CodexAddress,state:CodexState, *,
           detail:bool=False)->dict:
    root,codex=_valid(address,state)
    hero=state.player.base
    return {
        "schema":SCHEMA,
        "source_address":address.decimal_index,
        "game_started":True,
        "world_style":root.style,"lifecycle":root.lifecycle,
        "no_mandatory_win":root.lifecycle!="mandatory_completion",
        "current_turn":hero.turn,
        "world_era":state.era,
        "current_position":[hero.realm,hero.x,hero.y],
        "gameplay_actions":state.actions,
        "history_digest":state.history_digest,
        "domain_progress":{
            name:{"reputation":state.domain_reputation[n],
                  "axes":{axis:state.axis_mastery[n*8+i]
                          for i,axis in enumerate(DOMAIN_AXIS[name])}}
            for n,name in enumerate(DOMAINS)
        },
        "available_actions":available_actions(address,state),
        "gates":gate_catalog(address,state),
        "terrain":codex_cell(address,state),
        "player_resources":{
            "stamina":state.player.stamina,"hydration":state.player.hydration,
            "food":state.player.food,"knowledge":state.player.knowledge,
            "materials":state.player.material,"danger":state.player.danger,
        },
        "journeys":list(state.journeys),
        "axes_level_map":{axis:codex.values[i] for i,axis in
                          enumerate(AXIS_NAMES)} if detail else None,
        "claim":"game-state transitions for 128 axes and sixteen earned "
                "time-window passages; not rendered vehicle physics or AAA AI",
    }
