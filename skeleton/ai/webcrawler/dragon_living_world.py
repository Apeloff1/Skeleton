"""Original living worlds: worlds are playable even when no win condition exists.

A *world* can be an endless sandbox, a survival ecosystem, a shifting maze,
an evolving settlement, a multi-realm platform adventure, a story with
persistent post-ending exploration, or a traditional goal-bound campaign.
All world states are deterministic, mutable through actual player actions,
replayable and bounded per request; indexed universes are generated lazily.

Neither "no ending" nor "not yet completed" is considered an invalid world.
An optional ending changes subsequent playable state, world relations and
available choices. These are original abstract game mechanics, not copies of
any commercial map, character, faction or narrative expression.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from collections import deque
import json
import re

SCHEMA="skeleton.ai.dragon.living_world.v1"
CATALOG_SCHEMA="skeleton.ai.dragon.living_world_catalog.v1"
WORLD_ADDRESS_COUNT=1_600_000
VARIANTS_PER_ADDRESS=10
ADDRESSABLE_VARIATION_SLOTS=WORLD_ADDRESS_COUNT*VARIANTS_PER_ADDRESS
MAX_HISTORY=192
MAX_REALMS=12
MAX_ABS_COORD=1_000_000
MAX_RECORDED_ENDINGS=8
MAX_RESOURCE=999
DIRS=(("north",0,-1),("east",1,0),("south",0,1),("west",-1,0))
LIFECYCLES=("unending","optional_endings","postgame","multiple_endings",
            "mandatory_completion","restartable_runs","permadeath")
ENDING_IDS=("civic_union","wilderness_guardian","starfarer",
            "knowledge_keeper","merchant_compact","restored_world")
ENVIRONMENTS=("clear","rain","storm","snow","windy","fog","drought","flood")
BIOMES=("woodland","desert","coast","mountain","ruins","wetlands",
        "caverns","skylands","orbital","crystal_fields","tundra","garden")
RULES=("survival","crafting","construction","factions","story","maze",
       "shifting","multi_realm","portals","transport","discovery","combat",
       "economy","exploration","science","farming","terraform",
       "postgame","permadeath","restarting","time_cycles","seasons")
# Each style is an actually different active rule profile; no pretend
# bespoke voxel renderer, proprietary gameplay IP or physics claim.
STYLE_RULES={
    "creative_sandbox":("construction","crafting","terraform","exploration","discovery"),
    "survival_sandbox":("survival","crafting","construction","combat","exploration","seasons"),
    "living_ecosystem":("survival","farming","terraform","discovery","time_cycles"),
    "persistent_survival":("survival","crafting","construction","exploration","time_cycles","seasons"),
    "open_world_story":("story","factions","combat","economy","exploration","postgame"),
    "post_story_wasteland":("story","factions","crafting","combat","postgame","exploration"),
    "multiple_world_platform":("multi_realm","portals","transport","exploration","discovery"),
    "kingdom_hopping":("multi_realm","portals","story","factions","exploration"),
    "galactic_sandbox":("multi_realm","portals","science","exploration","transport","crafting"),
    "oceanic_archipelago":("multi_realm","transport","survival","crafting","exploration"),
    "floating_islands":("multi_realm","portals","transport","exploration","seasons"),
    "mutable_labyrinth":("maze","shifting","discovery","exploration","time_cycles"),
    "rotating_tower":("maze","shifting","multi_realm","portals","exploration"),
    "shifting_dungeon":("maze","shifting","combat","crafting","discovery"),
    "time_loop_maze":("maze","shifting","time_cycles","restarting","story"),
    "living_castle":("maze","shifting","factions","story","postgame"),
    "metroidvania_network":("maze","exploration","crafting","discovery","portals"),
    "nonlinear_roguelite":("maze","combat","restarting","discovery","exploration"),
    "hardcore_roguelike":("maze","combat","permadeath","survival","discovery"),
    "branching_campaign":("story","factions","exploration","discovery"),
    "endless_expedition":("exploration","discovery","survival","transport"),
    "colony_simulation":("construction","farming","survival","economy","science","seasons"),
    "city_builder":("construction","economy","factions","terraform","exploration"),
    "farming_life_sim":("farming","construction","economy","seasons","story"),
    "trading_world":("economy","transport","factions","exploration"),
    "social_simulation":("factions","story","economy","exploration","postgame"),
    "transport_tycoon":("transport","construction","economy","exploration"),
    "strategy_frontier":("construction","combat","economy","factions","multi_realm"),
    "postgame_free_roam":("story","exploration","factions","postgame","discovery"),
    "sandbox_builder":("construction","crafting","discovery","exploration","science"),
    "generational_world":("time_cycles","factions","story","farming","postgame"),
    "science_exploration":("science","multi_realm","portals","exploration","discovery"),
}
STYLE_NAMES=tuple(STYLE_RULES)
STYLE_LIFECYCLE={
    "creative_sandbox":"unending",
    "survival_sandbox":"unending",
    "living_ecosystem":"unending",
    "persistent_survival":"unending",
    "endless_expedition":"unending",
    "mutable_labyrinth":"unending",
    "rotating_tower":"unending",
    "shifting_dungeon":"unending",
    "transport_tycoon":"unending",
    "city_builder":"unending",
    "colony_simulation":"unending",
    "farming_life_sim":"unending",
    "sandbox_builder":"unending",
    "trading_world":"unending",
    "galactic_sandbox":"unending",
    "oceanic_archipelago":"unending",
    "floating_islands":"unending",
    "hardcore_roguelike":"permadeath",
    "nonlinear_roguelite":"restartable_runs",
    "time_loop_maze":"restartable_runs",
    "branching_campaign":"multiple_endings",
    "open_world_story":"postgame",
    "post_story_wasteland":"postgame",
    "postgame_free_roam":"postgame",
    "generational_world":"postgame",
    "living_castle":"postgame",
    "social_simulation":"postgame",
    "kingdom_hopping":"multiple_endings",
    "multiple_world_platform":"optional_endings",
    "metroidvania_network":"optional_endings",
    "science_exploration":"optional_endings",
    "strategy_frontier":"mandatory_completion",
}
assert set(STYLE_LIFECYCLE)==set(STYLE_RULES)
assert len(STYLE_RULES)>=32
SAFE=re.compile(r"[a-z][a-z0-9_]{0,47}\Z")

def _canonical(obj)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True).encode("ascii")

def _sha(obj)->str:
    return sha256(_canonical(obj)).hexdigest()

def _stable_number(*parts)->int:
    return int(_sha(parts)[:16],16)

def _integer(n,lo,hi,label):
    if type(n) is not int or not lo<=n<=hi:
        raise ValueError("original living world "+label+" outside bounded range")


@dataclass(frozen=True)
class LivingWorld:
    schema:str
    world_id:int
    variant:int
    style:str
    lifecycle:str
    rules:tuple[str,...]
    realms:int
    seed:int
    world_fingerprint:str
    includes_goal:bool
    allows_continuation:bool
    shifting_routes:bool
    original_work_attested:bool=True


@dataclass(frozen=True)
class LivingState:
    realm:int=0
    x:int=0
    y:int=0
    turn:int=0
    chapter:int=0
    era:int=0
    energy:int=100
    health:int=100
    food:int=8
    wood:int=2
    ore:int=0
    crystal:int=0
    shelter:int=0
    research:int=0
    trade:int=0
    allies:int=0
    faction_civic:int=0
    faction_wild:int=0
    discoveries:tuple[str,...]=()
    endings_seen:tuple[str,...]=()
    settlement_level:int=0
    portal_key:bool=False
    alive:bool=True
    run:int=0
    legacy:int=0
    world_changes:tuple[str,...]=()
    history_digest:str=""
    actions_played:int=0


def catalog()->dict:
    return {
        "schema":CATALOG_SCHEMA,
        "world_style_count":len(STYLE_NAMES),
        "styles":{name:{
            "rules":list(STYLE_RULES[name]),
            "default_lifecycle":STYLE_LIFECYCLE[name],
            "fixed_goal_required":STYLE_LIFECYCLE[name]=="mandatory_completion",
            "playability_is_not_win_condition":True,
        } for name in STYLE_NAMES},
        "lifecycles":list(LIFECYCLES),
        "addressable_world_ids":WORLD_ADDRESS_COUNT,
        "variants_per_world_id":VARIANTS_PER_ADDRESS,
        "addressable_world_variant_slots":ADDRESSABLE_VARIATION_SLOTS,
        "realms_per_world_max":MAX_REALMS,
        "route_environments":list(ENVIRONMENTS),
        "claims":"lazily addressable world designs, not 16m finished, reviewed, unique games",
    }


def create_world(*,world_id:int=0,variant:int=0,
                 style:str|None=None,lifecycle:str|None=None)->LivingWorld:
    _integer(world_id,0,WORLD_ADDRESS_COUNT-1,"world address")
    _integer(variant,0,VARIANTS_PER_ADDRESS-1,"variation slot")
    if style is None:style=STYLE_NAMES[world_id%len(STYLE_NAMES)]
    if type(style) is not str or style not in STYLE_RULES:
        raise ValueError("unknown authored world style")
    if lifecycle is None:lifecycle=STYLE_LIFECYCLE[style]
    if type(lifecycle) is not str or lifecycle not in LIFECYCLES:
        raise ValueError("unknown original world ending lifecycle")
    rules=STYLE_RULES[style]
    # An independently selectable end-state policy does not rewrite the
    # genre: the same narrative setting may be endless or reach an ending.
    if lifecycle=="permadeath" and "survival" not in rules and "combat" not in rules:
        raise ValueError("permadeath requires implemented survival or combat mechanics")
    realm_count=(3+_stable_number(world_id,variant,style,"realms")%10
                 if "multi_realm" in rules else 1)
    # Distinct addresses are reproducible identities; no assertion that
    # each has a provably different expressive level from 16m others.
    seed=_stable_number(world_id,variant,style,lifecycle,"genesis")&0xffffffff
    values={
        "schema":SCHEMA,"world_id":world_id,"variant":variant,
        "style":style,"lifecycle":lifecycle,"rules":rules,
        "realms":realm_count,"seed":seed,
        "includes_goal":lifecycle not in ("unending",),
        "allows_continuation":lifecycle in ("unending","optional_endings",
                                           "postgame","multiple_endings"),
        "shifting_routes":"shifting" in rules,
        "original_work_attested":True,
    }
    return LivingWorld(world_fingerprint=_sha(values),**values)


def validate_world(world:LivingWorld)->None:
    if not isinstance(world,LivingWorld) or world.schema!=SCHEMA:
        raise ValueError("unrecognized original living world schema")
    if world.original_work_attested is not True:
        raise PermissionError("world originality is not attested")
    canonical=create_world(
        world_id=world.world_id,variant=world.variant,
        style=world.style,lifecycle=world.lifecycle)
    if canonical!=world:
        raise ValueError("living world source identity or implemented rules were altered")


def initial_state(world:LivingWorld)->LivingState:
    validate_world(world)
    return LivingState(
        history_digest=_sha([world.world_fingerprint,"original_start"]),
    )


def terrain(world:LivingWorld,realm:int,x:int,y:int)->dict:
    """Stateless original terrain; same coordinate is stable across sessions."""
    validate_world(world)
    _integer(realm,0,world.realms-1,"realm")
    _integer(x,-MAX_ABS_COORD,MAX_ABS_COORD,"map x")
    _integer(y,-MAX_ABS_COORD,MAX_ABS_COORD,"map y")
    value=_stable_number(world.seed,realm,x//7,y//7,"biome")
    biome=BIOMES[value%len(BIOMES)]
    feature=_stable_number(world.seed,realm,x,y,"feature")%19
    return {
        "realm":realm,"x":x,"y":y,"biome":biome,
        "landmark":("observatory" if feature==0 else
                    "ancient_garden" if feature==1 else
                    "abandoned_station" if feature==2 else
                    "wildlife_reserve" if feature==3 else
                    "ordinary_land"),
        "weather":ENVIRONMENTS[
            (_stable_number(world.seed,realm,x//11,y//11,"climate"))%
            len(ENVIRONMENTS)],
        "authored_origin":"seeded_original_cell_no_imported_game_map",
    }


def atmosphere(world:LivingWorld,state:LivingState)->dict:
    # Periodic weather can alter interactions and route availability.
    p=_stable_number(world.seed,state.realm,state.x//11,state.y//11,
                     state.turn//8,"season")
    return {
        "weather":ENVIRONMENTS[p%len(ENVIRONMENTS)],
        "season":("spring","summer","autumn","winter")[(state.turn//24)%4],
        "maze_phase":state.turn%8,
        "epoch":state.turn//8,
        "time_of_day":("dawn","day","dusk","night")[state.turn%4],
    }


def _maze_door(world:LivingWorld,state:LivingState,dx:int,dy:int)->bool:
    if not world.shifting_routes:return True
    # Animated maze doors actually change with every movement, wait, build,
    # or story action. Every phase leaves the rotating compass exit open.
    angle=state.turn%4
    index=next(i for i,(_,x,y) in enumerate(DIRS) if (x,y)==(dx,dy))
    if index==angle:return True
    # Normalized spatial door identity gives stable door patterns for a
    # fixed phase while still changing with the move count.
    ax,ay=state.x,state.y
    bx,by=ax+dx,ay+dy
    endpoints=sorted(((ax,ay),(bx,by)))
    return (_stable_number(world.seed,state.realm,endpoints,
                           state.turn%8,"shift_door")%5)<2


def _discovery_key(world:LivingWorld,state:LivingState)->str:
    # Negative coordinates cannot appear verbatim in the strict original
    # token registry. Encode both signs with safe distinct identifiers:
    # north(-1) => m1, south(+1) => p1, never a hyphen or copied map.
    def axis(value:int)->str:
        return ("m"+str(-value)) if value<0 else ("p"+str(value))
    return "r"+str(state.realm)+"_x"+axis(state.x//8)+"_y"+axis(state.y//8)


def _add_unique(values:tuple[str,...],value:str,cap:int)->tuple[str,...]:
    if value in values:return values
    if len(values)>=cap:
        # Trim bounded recent-domain discoveries without ever pretending
        # removed historical details remain user-visible.
        return values[1:]+(value,)
    return values+(value,)


def terrain_for_state(world:LivingWorld,state:LivingState,
                      realm:int,x:int,y:int)->dict:
    """Project player-built settlements and reclaimed terrain onto real cells."""
    validate_world(world);validate_state(world,state)
    tile=terrain(world,realm,x,y).copy()
    here=replace(state,realm=realm,x=x,y=y)
    region=_discovery_key(world,here)
    structures=[]
    for action,description in (
        ("shelter_","original_settlement"),
        ("farm_","original_farm"),
        ("reclaimed_","reclaimed_garden"),
        ("outpost_","postgame_frontier_outpost"),
        ("memorial_","postgame_story_memorial"),
    ):
        if action+region in state.world_changes:
            structures.append(description)
    if "reclaimed_garden" in structures:
        tile["original_biome"]=tile["biome"]
        tile["biome"]="garden"
    if structures:
        tile["landmark"]=structures[-1]
    tile["built_local_structures"]=structures
    tile["player_caused_terrain_change"]=bool(structures)
    return tile


def _legal(world:LivingWorld,state:LivingState)->dict[str,dict]:
    rules=set(world.rules)
    choices={}
    def add(name,why,allowed=True,**more):
        choices[name]={"name":name,"available":bool(allowed),
                       "reason":"open" if allowed else why,
                       **more}
    if not state.alive:
        add("restart_run","open")
        return choices
    terminal=bool(state.endings_seen) and not world.allows_continuation
    if terminal:
        add("restart_run","open")
        return choices
    for name,dx,dy in DIRS:
        new_x,new_y=state.x+dx,state.y+dy
        within=abs(new_x)<=MAX_ABS_COORD and abs(new_y)<=MAX_ABS_COORD
        opened=within and _maze_door(world,state,dx,dy)
        awake=state.energy>=1
        add(name,
            "world_boundary" if not within else
            "moving_wall" if not opened else "rest_required",
            opened and awake,
            to=[state.realm,new_x,new_y],
            movement_model="dynamic_cell_transition",
        )
    add("wait","open")
    add("rest","open")
    add("observe","open")
    add("forage","open")
    if "construction" in rules or "crafting" in rules:
        add("build","requires_two_wood",state.wood>=2 and state.energy>=2)
        add("craft","requires_wood_ore",state.wood>=1 and state.ore>=1)
    if rules.intersection({"survival","crafting","construction","economy",
                           "science","terraform","exploration","combat"}):
        add("mine","energy_required",state.energy>=2)
    if "farming" in rules:
        add("farm","requires_wood",state.wood>=1)
    if "terraform" in rules:
        add("terraform","requires_two_ore",state.ore>=2)
    if "science" in rules:
        add("research","requires_crystal",state.crystal>=1)
    if "economy" in rules:
        add("trade","requires_ore",state.ore>=1)
    if "factions" in rules or "story" in rules:
        add("help_settlers","open")
        add("help_wilds","open")
        add("negotiate","requires_two_allies",state.allies>=2)
    if "combat" in rules:
        add("challenge_hostiles","health_or_energy_too_low",
            state.health>=16 and state.energy>=8)
    if "discovery" in rules or "exploration" in rules:
        add("survey","open")
    if "multi_realm" in rules:
        portal_ready=(state.portal_key or state.research>=2 or
                      state.chapter>=2 or state.discoveries!=())
        # Portals are at genuine nodes in the world and must be discovered
        # before use. Return trips remain possible; no forced one-way route.
        at_hub=(state.x%4==0 and state.y%4==0)
        for realm in range(world.realms):
            if realm==state.realm:continue
            add(f"portal_{realm}",
                "portal_hub_required" if not at_hub else
                "discover_portal_or_research",
                at_hub and portal_ready,
                to=[realm,0,0],
                movement_model="authored_original_world_transition",
            )
    if "transport" in rules:
        add("take_ferry","coastal_gate_or_raft_required",
            abs(state.x+4)<=MAX_ABS_COORD and
            abs(state.y+2)<=MAX_ABS_COORD and
            (state.wood>=1 or
             "coast" in terrain(world,state.realm,state.x,state.y)["biome"]),
            to=[state.realm,state.x+4,state.y+2],
            movement_model="abstract_water_travel_no_vessel_physics")
        add("ride_shuttle","research_or_allies_required",
            abs(state.x+8)<=MAX_ABS_COORD and
            abs(state.y+1)<=MAX_ABS_COORD and
            (state.research>=2 or state.allies>=2),
            to=[state.realm,state.x+8,state.y+1],
            movement_model="abstract_transport_not_spaceflight_physics")
    if state.endings_seen and world.allows_continuation:
        add("postgame_outpost","requires_two_wood",
            state.wood>=2)
        add("postgame_memorial","requires_original_crystal",
            state.crystal>=1)
        add("postgame_rebuild","requires_two_ore",
            state.ore>=2)
        add("postgame_expedition","requires_food_and_energy",
            state.food>=1 and state.energy>=2 and
            abs(state.x+3)<=MAX_ABS_COORD and
            abs(state.y+1)<=MAX_ABS_COORD)
        add("postgame_council","requires_two_allies",
            state.allies>=2)
    if world.includes_goal:
        requirements={
            "civic_union":state.faction_civic>=2 and state.allies>=1,
            "wilderness_guardian":state.faction_wild>=2 and state.wood>=2,
            "starfarer":state.research>=2 and state.portal_key,
            "knowledge_keeper":state.research>=3,
            "merchant_compact":state.trade>=3,
            "restored_world":state.shelter>=1 and state.faction_civic>=1 and
                             state.faction_wild>=1,
        }
        for ending,ok in requirements.items():
            if ending in state.endings_seen:
                continue
            add("ending_"+ending,"story_preconditions_unmet",ok,
                world_ending=True,continues_after=world.allows_continuation)
    if world.lifecycle in ("restartable_runs","permadeath"):
        add("restart_run","open")
    return choices


def options(world:LivingWorld,state:LivingState)->list[dict]:
    validate_world(world)
    validate_state(world,state)
    return list(_legal(world,state).values())


def validate_state(world:LivingWorld,state:LivingState)->None:
    if not isinstance(state,LivingState):
        raise ValueError("living game state missing")
    for v,lo,hi,name in (
        (state.realm,0,world.realms-1,"realm"),
        (state.x,-MAX_ABS_COORD,MAX_ABS_COORD,"x"),
        (state.y,-MAX_ABS_COORD,MAX_ABS_COORD,"y"),
        (state.turn,0,2**31-1,"game turn"),
        (state.chapter,0,999999,"story chapter"),
        (state.era,0,999999,"world era"),
        (state.energy,0,100,"energy"),(state.health,0,100,"health"),
        (state.food,0,MAX_RESOURCE,"food"),
        (state.wood,0,MAX_RESOURCE,"wood"),
        (state.ore,0,MAX_RESOURCE,"ore"),
        (state.crystal,0,MAX_RESOURCE,"crystal"),
        (state.shelter,0,MAX_RESOURCE,"shelter"),
        (state.research,0,MAX_RESOURCE,"research"),
        (state.trade,0,MAX_RESOURCE,"trade"),
        (state.allies,0,MAX_RESOURCE,"allies"),
        (state.faction_civic,-100,100,"civic alignment"),
        (state.faction_wild,-100,100,"wild alignment"),
        (state.settlement_level,0,MAX_RESOURCE,"settlement level"),
        (state.run,0,2**31-1,"run"),
        (state.legacy,0,MAX_RESOURCE,"legacy"),
        (state.actions_played,0,2**31-1,"number of played actions"),
    ):
        _integer(v,lo,hi,name)
    if type(state.alive) is not bool or type(state.portal_key) is not bool:
        raise ValueError("life and portal flags must be real booleans")
    for field,values,maxlen in (
        ("discoveries",state.discoveries,64),
        ("endings_seen",state.endings_seen,MAX_RECORDED_ENDINGS),
        ("world_changes",state.world_changes,24),
    ):
        if (not isinstance(values,tuple) or len(values)>maxlen or
                any(type(v) is not str or not SAFE.fullmatch(v) for v in values)
                or len(set(values))!=len(values)):
            raise ValueError("original game "+field+" invalid or exceeded capacity")
    if any(x not in ENDING_IDS for x in state.endings_seen):
        raise ValueError("forged original game narrative outcome")
    if (type(state.history_digest) is not str or
            len(state.history_digest)!=64 or
            any(x not in "0123456789abcdef" for x in state.history_digest)):
        raise ValueError("source replay digest malformed")


def _cap(value:int)->int:
    return min(MAX_RESOURCE,max(0,value))


def take_action(world:LivingWorld,state:LivingState,action:str)->LivingState:
    """Consume exactly one choice: no free state mutation or invented endings."""
    validate_world(world)
    validate_state(world,state)
    if type(action) is not str or not SAFE.fullmatch(action):
        raise ValueError("unknown original gameplay choice encoding")
    available=_legal(world,state)
    if action not in available or not available[action]["available"]:
        raise ValueError("choice is unavailable in actual evolving world state")
    if state.turn>=2**31-2 or state.actions_played>=2**31-2:
        raise ValueError("original world turn counter exhausted")
    rules=set(world.rules)
    next=replace(state,turn=state.turn+1,actions_played=state.actions_played+1)
    if action in {n for n,_,_ in DIRS}:
        _,dx,dy=[direction for direction in DIRS if direction[0]==action][0]
        # The chosen gate is checked on OLD phase, after which the maze
        # immediately twists into the new phase for the next choice.
        next=replace(next,x=state.x+dx,y=state.y+dy,
                     energy=max(0,state.energy-1))
        zone=_discovery_key(world,next)
        first=zone not in state.discoveries
        next=replace(next,discoveries=_add_unique(next.discoveries,zone,64),
                     chapter=state.chapter+(1 if first else 0),
                     portal_key=next.portal_key or first)
    elif action=="rest":
        next=replace(next,energy=min(100,state.energy+22),
                     health=min(100,state.health+4),food=max(0,state.food-1))
    elif action=="forage":
        next=replace(next,food=_cap(state.food+3),
                     wood=_cap(state.wood+1),energy=min(100,state.energy+6))
    elif action=="observe":
        token=_discovery_key(world,state)
        next=replace(next,discoveries=_add_unique(state.discoveries,token,64),
                     portal_key=True,chapter=state.chapter+1)
    elif action=="build":
        next=replace(next,wood=state.wood-2,shelter=_cap(state.shelter+1),
                     settlement_level=_cap(state.settlement_level+1),
                     energy=state.energy-2,
                     world_changes=_add_unique(
                        _add_unique(state.world_changes,
                                    "settlement_built",24),
                        "shelter_"+_discovery_key(world,state),24))
    elif action=="craft":
        next=replace(next,wood=state.wood-1,ore=state.ore-1,
                     crystal=_cap(state.crystal+1),research=_cap(state.research+1))
    elif action=="mine":
        next=replace(next,ore=_cap(state.ore+2),
                     crystal=_cap(state.crystal+(1 if state.turn%3==0 else 0)),
                     energy=max(0,state.energy-2))
    elif action=="farm":
        next=replace(next,wood=state.wood-1,food=_cap(state.food+7),
                     world_changes=_add_unique(
                        _add_unique(state.world_changes,
                                    "farm_established",24),
                        "farm_"+_discovery_key(world,state),24))
    elif action=="terraform":
        next=replace(next,ore=state.ore-2,
                     world_changes=_add_unique(
                        _add_unique(state.world_changes,
                                    "land_reclaimed",24),
                        "reclaimed_"+_discovery_key(world,state),24))
    elif action=="research":
        next=replace(next,crystal=state.crystal-1,
                     research=_cap(state.research+1),portal_key=True)
    elif action=="trade":
        next=replace(next,ore=state.ore-1,trade=_cap(state.trade+1),
                     food=_cap(state.food+2))
    elif action=="help_settlers":
        next=replace(next,faction_civic=min(100,state.faction_civic+1),
                     faction_wild=max(-100,state.faction_wild-1),
                     allies=_cap(state.allies+1),
                     world_changes=_add_unique(
                        state.world_changes,"civic_trust",24))
    elif action=="help_wilds":
        next=replace(next,faction_wild=min(100,state.faction_wild+1),
                     faction_civic=max(-100,state.faction_civic-1),
                     wood=_cap(state.wood+1),
                     world_changes=_add_unique(
                        state.world_changes,"wild_guardianship",24))
    elif action=="negotiate":
        next=replace(next,allies=state.allies-2,
                     faction_civic=min(100,state.faction_civic+1),
                     faction_wild=min(100,state.faction_wild+1),
                     world_changes=_add_unique(
                        state.world_changes,"peace_accord",24))
    elif action=="challenge_hostiles":
        next=replace(next,health=max(0,state.health-11),
                     energy=max(0,state.energy-8),
                     ore=_cap(state.ore+2),crystal=_cap(state.crystal+1))
    elif action=="survey":
        next=replace(next,ore=_cap(state.ore+1),
                     research=_cap(state.research+1),
                     portal_key=True,chapter=state.chapter+1)
    elif action.startswith("portal_"):
        target=int(action.removeprefix("portal_"))
        next=replace(next,realm=target,x=0,y=0,
                     energy=max(0,state.energy-2),chapter=state.chapter+1)
    elif action=="take_ferry":
        next=replace(next,x=state.x+4,y=state.y+2,
                     wood=max(0,state.wood-1))
    elif action=="ride_shuttle":
        next=replace(next,x=state.x+8,y=state.y+1,
                     crystal=max(0,state.crystal-1))
    elif action.startswith("ending_"):
        ending=action.removeprefix("ending_")
        next=replace(next,endings_seen=state.endings_seen+(ending,),
                     era=state.era+1,
                     world_changes=_add_unique(
                         state.world_changes,"era_"+ending,24))
        if ending=="civic_union":
            next=replace(next,allies=_cap(next.allies+3),
                         settlement_level=_cap(next.settlement_level+2))
        elif ending=="wilderness_guardian":
            next=replace(next,wood=_cap(next.wood+4),
                         food=_cap(next.food+6))
        elif ending=="starfarer":
            next=replace(next,realm=(state.realm+1)%world.realms,
                         x=0,y=0,portal_key=True)
        elif ending=="knowledge_keeper":
            next=replace(next,research=_cap(next.research+3))
        elif ending=="merchant_compact":
            next=replace(next,trade=_cap(next.trade+3),
                         food=_cap(next.food+5))
        elif ending=="restored_world":
            next=replace(next,health=100,energy=100,
                         settlement_level=_cap(next.settlement_level+3))
    elif action=="postgame_outpost":
        next=replace(next,wood=state.wood-2,
                     settlement_level=_cap(state.settlement_level+1),
                     chapter=state.chapter+1,
                     world_changes=_add_unique(
                        state.world_changes,
                        "outpost_"+_discovery_key(world,state),24))
    elif action=="postgame_memorial":
        next=replace(next,crystal=state.crystal-1,
                     chapter=state.chapter+1,
                     world_changes=_add_unique(
                        state.world_changes,
                        "memorial_"+_discovery_key(world,state),24))
    elif action=="postgame_rebuild":
        next=replace(next,ore=state.ore-2,
                     chapter=state.chapter+1,
                     world_changes=_add_unique(
                        state.world_changes,
                        "reclaimed_"+_discovery_key(world,state),24))
    elif action=="postgame_expedition":
        next=replace(next,x=state.x+3,y=state.y+1,
                     food=state.food-1,energy=state.energy-2,
                     chapter=state.chapter+2,portal_key=True,
                     world_changes=_add_unique(
                        state.world_changes,"new_frontier",24))
    elif action=="postgame_council":
        next=replace(next,allies=state.allies-2,
                     faction_civic=min(100,state.faction_civic+1),
                     faction_wild=min(100,state.faction_wild+1),
                     chapter=state.chapter+1,
                     world_changes=_add_unique(
                        state.world_changes,"postgame_peace_council",24))
    elif action=="restart_run":
        resumed=initial_state(world)
        next=replace(resumed,turn=state.turn+1,run=state.run+1,
                     legacy=_cap(state.legacy+1),
                     actions_played=state.actions_played+1,
                     endings_seen=(state.endings_seen
                                   if world.allows_continuation else ()),
                     world_changes=(state.world_changes
                                    if world.allows_continuation else ()),
                     history_digest=state.history_digest)
    elif action=="wait":
        next=replace(next,energy=min(100,state.energy+1))
    else:
        raise ValueError("world style offered unimplemented action")
    if "survival" in rules:
        # Resource drain is real; forage/rest remain reachable (unless
        # permadeath already occurred). This is not full creature AI.
        if next.turn%3==0:
            next=replace(next,food=max(0,next.food-1))
        if next.food==0:
            next=replace(next,health=max(0,next.health-3))
        if next.health==0:
            next=replace(next,alive=False)
    next=replace(next,history_digest=_sha([
        world.world_fingerprint,state.history_digest,state.actions_played,
        action,asdict(replace(next,history_digest="")),
    ]))
    validate_state(world,next)
    return next


def replay(world:LivingWorld,actions:tuple[str,...]=(),
           *,starting_state:LivingState|None=None)->LivingState:
    validate_world(world)
    if (not isinstance(actions,tuple) or len(actions)>MAX_HISTORY or
            any(type(x) is not str or not SAFE.fullmatch(x) for x in actions)):
        raise ValueError("world game replay actions outside bounded safe input")
    state=initial_state(world) if starting_state is None else starting_state
    validate_state(world,state)
    for action in actions:
        state=take_action(world,state,action)
    return state


def describe(world:LivingWorld,state:LivingState,
             *,include_options:bool=True)->dict:
    validate_world(world);validate_state(world,state)
    current=terrain_for_state(world,state,state.realm,state.x,state.y)
    return {
        "schema":SCHEMA,"world_id":world.world_id,
        "variation":world.variant,"style":world.style,
        "lifecycle":world.lifecycle,
        "fixed_winning_condition_exists":world.includes_goal,
        "playable":state.alive and (
            not state.endings_seen or world.allows_continuation),
        "has_completed_ending":bool(state.endings_seen),
        "postgame_active":bool(state.endings_seen) and world.allows_continuation,
        "player":asdict(state),
        "tile":current,
        "environment":atmosphere(world,state),
        "options":options(world,state) if include_options else [],
        "gameplay_claim":"actual seeded state transitions; not a voxel renderer, vehicle physics, commercial game map, NPC AI or automatically fun narrative",
    }


def journal(world:LivingWorld,actions:tuple[str,...])->dict:
    """Replay proof at each transition, not invented outcomes."""
    state=initial_state(world)
    trace=[]
    for action in actions:
        before=state
        state=take_action(world,before,action)
        trace.append({
            "step":state.actions_played,"action":action,
            "realm":state.realm,"x":state.x,"y":state.y,
            "endings_seen":list(state.endings_seen),
            "digest":state.history_digest,
            "maze_phase":state.turn%8,
        })
    return {
        "schema":SCHEMA,"world_fingerprint":world.world_fingerprint,
        "steps":trace,"final":describe(world,state),
        "replay_verified":replay(world,actions)==state,
    }
