"""Executable genomic world rules: 24 axes alter real materials, travel and choices.

Every genome axis has a corresponding *playable* action and numeric response,
with deterministic finite-time environmental projection. Unlimited indexed
combinations are generated on demand; no eager enumeration. This is an
original turn-based world simulation, not a 3D render/physics SDK.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from hashlib import sha256
import json

from .dragon_living_world import (
    LivingWorld,LivingState,create_world,initial_state,validate_world,
    validate_state,take_action,terrain_for_state,atmosphere,options,
    DIRS,_stable_number,_sha,MAX_ABS_COORD,
)
from .dragon_world_genome import (
    Genome,WorldGenomeAddress,AXIS_NAMES,genome_world,genome_code,
)
SCHEMA="skeleton.ai.dragon.genomic_world_play.v1"
MAX_ACTIONS_PER_REPLAY=128
MAX_METER=100_000
# Each command has a genuine state effect indexed by exactly one meaningful
# world axis. All 24 are usable in unending games without a mandatory goal.
AXIS_ACTIONS=(
    "survey_elevation",
    "map_biomes",
    "study_river",
    "explore_caves",
    "scan_skies",
    "forecast_storm",
    "study_seasons",
    "chart_stars",
    "tend_flora",
    "track_fauna",
    "forage_food",
    "prospect_ore",
    "plan_building",
    "found_outpost",
    "trade_goods",
    "mediate_dispute",
    "defend_camp",
    "scout_pass",
    "trace_shifting_wall",
    "stabilize_portal",
    "seek_relic",
    "research_ruins",
    "record_choice",
    "renew_ecology",
)
assert len(AXIS_ACTIONS)==len(AXIS_NAMES)
TRAVEL_ACTIONS=("ride_river","climb_ridge","glide_sky","cave_shortcut",
                "cross_gate")

@dataclass(frozen=True)
class GenomicState:
    base:LivingState
    stamina:int=100
    hydration:int=60
    food:int=12
    material:int=6
    credits:int=5
    knowledge:int=0
    community:int=0
    ecology:int=40
    danger:int=0
    infrastructure:int=0
    portal_charge:int=0
    choices:int=0
    signals:tuple[int,...]=(0,)*24
    history_digest:str=""


def _valid(state:GenomicState,world:LivingWorld)->None:
    if not isinstance(state,GenomicState):
        raise ValueError("genomic game needs actual typed player state")
    validate_state(world,state.base)
    for key in ("stamina","hydration","food","material","credits","knowledge",
                "community","ecology","danger","infrastructure",
                "portal_charge","choices"):
        value=getattr(state,key)
        if type(value) is not int or not 0<=value<=MAX_METER:
            raise ValueError("genomic game state contains invalid "+key)
    if (type(state.signals) is not tuple or len(state.signals)!=24 or
        any(type(x) is not int or not 0<=x<=MAX_METER for x in state.signals)):
        raise ValueError("world simulation event vector outside bounds")
    if (type(state.history_digest) is not str or len(state.history_digest)!=64
        or any(x not in "0123456789abcdef" for x in state.history_digest)):
        raise ValueError("gameplay history receipt malformed")


def initial_genomic_state(address:WorldGenomeAddress)->GenomicState:
    world,genes=genome_world(address)
    first=GenomicState(
        base=initial_state(world),
        stamina=max(32,100-genes.get("traversal_drag")*2),
        hydration=60+genes.get("watershed")*2,
        food=6+genes.get("food_bounty"),
        material=2+genes.get("mineral_density"),
        credits=5+genes.get("market_cycle"),
        community=genes.get("diplomacy_tension"),
        ecology=40+genes.get("flora_dynamics"),
        infrastructure=genes.get("settlement_growth"),
        portal_charge=genes.get("portal_instability"),
        history_digest=_sha([SCHEMA,address.genome_digest,"genesis"]),
    )
    _valid(first,world)
    return first


def _cap(value:int)->int:
    return max(0,min(MAX_METER,value))


def cell(address:WorldGenomeAddress,state:GenomicState,
         realm:int,x:int,y:int)->dict:
    world,genes=genome_world(address)
    _valid(state,world)
    if (type(realm) is not int or not 0<=realm<world.realms or
        type(x) is not int or not -MAX_ABS_COORD<=x<=MAX_ABS_COORD or
        type(y) is not int or not -MAX_ABS_COORD<=y<=MAX_ABS_COORD):
        raise ValueError("authored genomic terrain cell outside world boundaries")
    local=terrain_for_state(world,state.base,realm,x,y)
    phase=state.base.turn
    noise=_stable_number(address.genome_digest,realm,x//3,y//3,"geology")
    weather=_stable_number(address.genome_digest,realm,x//7,y//7,
                           phase//(1+genes.get("season_clock")),"climate")
    g=genes.levels
    # Signals are distinct *physical/experiential* inputs. Their values
    # affect real actions and resource outcomes in play(), not merely tags.
    measurements={
        "elevation":(noise%21)+g[0]*3,
        "biome_diversity":(noise>>3)%10+g[1],
        "water_depth":(weather%11)+g[2]*2,
        "cave_layers":(noise>>7)%7+g[3],
        "sky_density":(noise>>11)%8+g[4],
        "storm_pressure":(weather>>3)%10+g[5]*2,
        "season_length":1+g[6],
        "day_length":2+g[7],
        "flora_cover":(noise>>13)%12+g[8]*2,
        "fauna_pressure":(noise>>17)%8+g[9],
        "food_yield":1+g[10],
        "mineral_yield":1+g[11],
        "building_cost":1+g[12],
        "settlement_growth":1+g[13],
        "market_spread":1+g[14],
        "diplomacy_cost":1+g[15],
        "hostile_intensity":1+g[16],
        "travel_friction":1+g[17],
        "maze_shift_period":1+g[18],
        "portal_turbulence":1+g[19],
        "discovery_cost":1+g[20],
        "research_yield":1+g[21],
        "choice_impact":1+g[22],
        "world_renewal":1+g[23],
    }
    # All 24 measurements are used in the player action rules. No
    # guarantees about the human perceptual distinctness of all addresses.
    local.update({
        "genome_cell_sha256":_sha([
            address.genome_digest,realm,x,y,phase,measurements,
        ]),
        "genomic_environment":measurements,
        "genomic_season":(phase//measurements["season_length"])%4,
        "genomic_day_phase":(phase//measurements["day_length"])%4,
        "terrain_affects_gameplay":True,
        "source_claim":"original deterministic terrain signals and real turn actions",
    })
    return local


def _move_cost(local:dict,state:GenomicState)->int:
    e=local["genomic_environment"]
    return (1+e["travel_friction"]//4+e["elevation"]//20+
            e["storm_pressure"]//12+
            (1 if state.hydration<10 else 0))


def legal_actions(address:WorldGenomeAddress,state:GenomicState)->list[dict]:
    world,genes=genome_world(address)
    _valid(state,world)
    local=cell(address,state,state.base.realm,state.base.x,state.base.y)
    env=local["genomic_environment"]
    results=[]
    for old in options(world,state.base):
        action=old["name"]
        good=bool(old["available"])
        reason=old["reason"]
        if action in {entry[0] for entry in DIRS} and (
            state.stamina<_move_cost(local,state) or state.hydration==0):
            good=False
            reason="genomic_stamina_or_hydration_required"
        results.append({
            **old,"available":good,
            "reason":"open" if good else reason,
            "genomic_cost":_move_cost(local,state)
                           if action in {entry[0] for entry in DIRS} else 0,
            "source":"canonical_original_world_transition",
        })
    # Every editable axis has exactly one concrete verb, never fake
    # per-genome choices advertised without a working transition.
    for index,action in enumerate(AXIS_ACTIONS):
        allowed=True
        if action=="found_outpost":
            allowed=state.material>=env["building_cost"]
        elif action=="trade_goods":
            allowed=state.material>=1
        elif action=="climb_ridge":
            allowed=state.stamina>=6
        elif action=="defend_camp":
            allowed=state.stamina>=2
        results.append({
            "name":action,"available":allowed,
            "reason":"open" if allowed else "world_resources_required",
            "physical_axis":AXIS_NAMES[index],
            "source":"playable_genomic_simulation_action",
            "strength":genes.levels[index]+1,
        })
    routes={
        "ride_river":env["water_depth"]>=13 and state.material>=1,
        "climb_ridge":env["elevation"]>=25 and state.stamina>=7,
        "glide_sky":env["sky_density"]>=10 and state.portal_charge>=1,
        "cave_shortcut":env["cave_layers"]>=10 and state.stamina>=5,
        "cross_gate":state.portal_charge>=10 and state.knowledge>=3,
    }
    for name,allowed in routes.items():
        results.append({
            "name":name,"available":allowed,
            "reason":"open" if allowed else "regional_physics_or_technology_gate",
            "source":"conditional_original_environmental_travel",
        })
    return results


def play(address:WorldGenomeAddress,state:GenomicState,action:str)->GenomicState:
    world,genes=genome_world(address)
    _valid(state,world)
    if (type(action) is not str or not 1<=len(action)<=48 or
        any(not(c.islower() or c.isdigit() or c=="_") for c in action)):
        raise ValueError("original genome action syntax invalid")
    choices={item["name"]:item for item in legal_actions(address,state)}
    if action not in choices or not choices[action]["available"]:
        raise ValueError("original genomic route or resource action is not available")
    here=cell(address,state,state.base.realm,state.base.x,state.base.y)
    env=here["genomic_environment"]
    if state.choices>=MAX_METER:
        raise ValueError("original world event counter exceeds safe capacity")
    # Every custom action advances the *canonical* world time and may discover
    # normal world content. Recalculate its source receipt with actual effects.
    baseline_action=("forage" if action in (
        "tend_flora","forage_food","prospect_ore","found_outpost",
        "trade_goods","defend_camp","renew_ecology")
        else "rest" if action in ("forecast_storm","study_seasons") else
        "observe")
    if action in {item["name"] for item in options(world,state.base)}:
        baseline_action=action
    latest=take_action(world,state.base,baseline_action)
    updates={}
    signals=list(state.signals)
    stress=(env["hostile_intensity"]+env["fauna_pressure"])//9
    # The survival pressure is bounded and recoverable by 'rest' and
    # 'forage', not an implicit false mandatory victory condition.
    stamina=state.stamina
    hydration=state.hydration
    danger=state.danger
    if action in {entry[0] for entry in DIRS}:
        stamina=_cap(state.stamina-_move_cost(here,state))
        hydration=_cap(state.hydration-1-env["storm_pressure"]//15)
        danger=_cap(state.danger+stress)
        updates["knowledge"]=_cap(
            state.knowledge+env["biome_diversity"]//5)
    elif action=="rest":
        stamina=_cap(stamina+20+env["flora_cover"]//8)
        hydration=_cap(hydration+3+env["water_depth"]//5)
        danger=_cap(danger-3)
    elif action=="forage":
        updates["food"]=_cap(state.food+env["food_yield"])
        hydration=_cap(hydration+env["water_depth"]//4+1)
        stamina=_cap(stamina+3)
    elif action=="wait":
        stamina=_cap(stamina+1)
    if action in AXIS_ACTIONS:
        index=AXIS_ACTIONS.index(action)
        level=genes.levels[index]+1
        signals[index]=_cap(signals[index]+level)
        if index==0:updates["knowledge"]=_cap(state.knowledge+level)
        elif index==1:updates["knowledge"]=_cap(state.knowledge+level*2)
        elif index==2:hydration=_cap(hydration+level*3)
        elif index==3:updates["material"]=_cap(state.material+level)
        elif index==4:updates["portal_charge"]=_cap(state.portal_charge+level)
        elif index==5:danger=_cap(danger-level)
        elif index==6:updates["community"]=_cap(state.community+level)
        elif index==7:updates["knowledge"]=_cap(state.knowledge+level)
        elif index==8:updates["ecology"]=_cap(state.ecology+level)
        elif index==9:danger=_cap(danger+level//2)
        elif index==10:updates["food"]=_cap(state.food+level*2)
        elif index==11:updates["material"]=_cap(state.material+level*2)
        elif index==12:updates["knowledge"]=_cap(state.knowledge+level)
        elif index==13:
            updates["material"]=state.material-env["building_cost"]
            updates["infrastructure"]=_cap(state.infrastructure+level)
        elif index==14:
            updates["material"]=state.material-1
            updates["credits"]=_cap(state.credits+level*2)
        elif index==15:updates["community"]=_cap(state.community+level)
        elif index==16:
            stamina=_cap(stamina-2)
            danger=_cap(danger-level)
            updates["material"]=_cap(state.material+level)
        elif index==17:stamina=_cap(stamina+level)
        elif index==18:updates["knowledge"]=_cap(state.knowledge+level)
        elif index==19:updates["portal_charge"]=_cap(state.portal_charge+level)
        elif index==20:updates["knowledge"]=_cap(state.knowledge+level)
        elif index==21:updates["knowledge"]=_cap(state.knowledge+level*2)
        elif index==22:updates["community"]=_cap(state.community+level*2)
        elif index==23:updates["ecology"]=_cap(state.ecology+level*2)
    elif action in TRAVEL_ACTIONS:
        dx,dy={
            "ride_river":(4,1),"climb_ridge":(0,-3),
            "glide_sky":(5,-2),"cave_shortcut":(-3,-1),
            "cross_gate":(7,0),
        }[action]
        if (abs(state.base.x+dx)>MAX_ABS_COORD or
            abs(state.base.y+dy)>MAX_ABS_COORD):
            raise ValueError("original transport goes beyond playable world boundary")
        latest=replace(latest,x=state.base.x+dx,y=state.base.y+dy)
        stamina=_cap(stamina-3)
        hydration=_cap(hydration-2)
        updates["knowledge"]=_cap(state.knowledge+2)
        if action in ("ride_river","cross_gate"):
            updates["material"]=_cap(state.material-1)
        if action in ("glide_sky","cross_gate"):
            updates["portal_charge"]=_cap(state.portal_charge-1)
    # Canonical engine retains its original authored endings and chapters.
    # Genomic simulation never fabricates a win when none exists.
    next_state=replace(
        state,base=latest,stamina=stamina,hydration=hydration,
        danger=danger,signals=tuple(signals),choices=state.choices+1,
        **updates,
    )
    # Receipt includes exact physical effects; executing the same action
    # under a different genome produces a different evidence chain.
    proof=_sha([SCHEMA,address.genome_digest,state.history_digest,
                action,asdict(replace(next_state,history_digest=""))])
    next_state=replace(next_state,history_digest=proof)
    _valid(next_state,world)
    return next_state


def replay_genomic(address:WorldGenomeAddress,actions:tuple[str,...]=(),
                   *,start:GenomicState|None=None)->GenomicState:
    if (type(actions) is not tuple or len(actions)>MAX_ACTIONS_PER_REPLAY or
        any(type(a) is not str or len(a)>48 for a in actions)):
        raise ValueError("original genome route actions outside bounded replay")
    world,genes=genome_world(address)
    current=initial_genomic_state(address) if start is None else start
    _valid(current,world)
    for action in actions:
        current=play(address,current,action)
    return current


def report(address:WorldGenomeAddress,state:GenomicState,
           *,radius:int=1)->dict:
    world,genes=genome_world(address)
    _valid(state,world)
    if type(radius) is not int or not 0<=radius<=3:
        raise ValueError("genomic terrain viewport exceeds 7x7 cells")
    area=[]
    for y in range(state.base.y-radius,state.base.y+radius+1):
        for x in range(state.base.x-radius,state.base.x+radius+1):
            if abs(x)<=MAX_ABS_COORD and abs(y)<=MAX_ABS_COORD:
                area.append(cell(address,state,state.base.realm,x,y))
    return {
        "schema":SCHEMA,"address":address.decimal_index,
        "genome_digest":address.genome_digest,
        "style":address.style,"lifecycle":address.lifecycle,
        "has_mandatory_win":world.lifecycle=="mandatory_completion",
        "has_possible_ending":world.includes_goal,
        "experienced_endings":list(state.base.endings_seen),
        "playable":state.base.alive and (
            not state.base.endings_seen or world.allows_continuation),
        "postgame":bool(state.base.endings_seen) and world.allows_continuation,
        "player":asdict(state),
        "local_terrain":area,
        "actions":legal_actions(address,state),
        "physical_controls":genes.effects(),
        "audit_scope":"actual canonical world transitions plus 24 material "
                      "world-control actions and five environment-gated transports; "
                      "not human-judged game uniqueness or finished 3D game",
    }
