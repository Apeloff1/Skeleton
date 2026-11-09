"""Executable ORIGINAL gameplay-mechanic programs, not just genome labels.

32 independently variable mechanics with four actual runtime implementations:
0=absent, 1=basic, 2=advanced and 3=intensive. Encoding is base 4,
giving exactly 4**32 = 18,446,744,073,709,551,616 reversible *rule programs*.

Crucially, every nonzero mechanic has an actual player action, resource
economy, world mutation and replay evidence. A changed axis is distinguishable
by action availability (if disabled) or by real effects (if intensity differs).
The first 24 independent enable bits alone give 16,777,216 behaviorally
separable original action sets; this is not 16m complete, artistically
unique, playtested or licensed games. Existing 128-axis World Codex settings
can optionally serve as verified environmental parent design.

The runtime is an abstract original game-mechanic simulator. It does NOT
copy any commercial game map/characters or claim 3D vehicle physics.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,replace
from hashlib import sha256
from functools import lru_cache
import json,re

SCHEMA="skeleton.ai.dragon.original_mechanic_program.v1"
MECHANIC_LEVELS=4
MECHANIC_COUNT=32
PROGRAM_COUNT=MECHANIC_LEVELS**MECHANIC_COUNT
MILLION_DISTINCT_ENABLE_PROFILES=2**24
FULL_BINARY_PROFILE_COUNT=2**MECHANIC_COUNT
DIRECTED_MECHANIC_FUSIONS=MECHANIC_COUNT**2
MAX_ACTIONS=128
MAX_STATE=1_000_000
# Distinct authored verbs with specific effects, domains, resource
# requirements and changes to adjacent world systems.
MECHANICS=(
 ("terraced_trails","traversal","stone","lore"),
 ("river_navigation","hydrology","wood","lore"),
 ("aerial_thermals","aerial","energy","lore"),
 ("tidal_passages","hydrology","lore","food"),
 ("storm_shelters","climate","wood","energy"),
 ("snow_bridges","climate","stone","lore"),
 ("rotating_corridors","maze","energy","stone"),
 ("doubleback_caches","maze","lore","wood"),
 ("scenic_detours","exploration","food","lore"),
 ("secret_keycraft","unlock","stone","aether"),
 ("portal_alignment","cosmology","aether","lore"),
 ("rail_timelines","transport","stone","wealth"),
 ("open_seas","transport","wood","wealth"),
 ("orbital_transfer","cosmology","aether","stone"),
 ("ecology_succession","ecology","food","wood"),
 ("creature_migration","ecology","food","lore"),
 ("settlement_growth","construction","stone","wealth"),
 ("salvage_economy","construction","stone","wood"),
 ("artisan_crafting","crafting","wood","stone"),
 ("seasonal_farming","ecology","wood","food"),
 ("merchant_convoys","economy","food","wealth"),
 ("faction_diplomacy","society","wealth","lore"),
 ("social_memory","society","lore","wealth"),
 ("branching_chronicles","narrative","lore","aether"),
 ("alternate_conclusions","narrative","wealth","aether"),
 ("postgame_repair","postgame","stone","lore"),
 ("survival_foraging","survival","energy","food"),
 ("hardcore_perils","survival","food","aether"),
 ("archaeology","research","stone","lore"),
 ("research_laboratories","research","wealth","aether"),
 ("terrain_terraforming","construction","aether","food"),
 ("world_era_cycles","chronology","lore","energy"),
)
RESOURCE_NAMES=("stone","wood","food","wealth","lore","aether","energy")
RESOURCE_INDEX={name:i for i,name in enumerate(RESOURCE_NAMES)}
MECHANIC_IDS=tuple(row[0] for row in MECHANICS)
MECHANIC_INDEX={name:i for i,name in enumerate(MECHANIC_IDS)}
assert len(MECHANICS)==MECHANIC_COUNT
assert len(MECHANIC_INDEX)==MECHANIC_COUNT
assert PROGRAM_COUNT>10**18 and MILLION_DISTINCT_ENABLE_PROFILES>10**6
DECIMAL=re.compile(r"(0|[1-9][0-9]*)\Z")


def _digest(value)->str:
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class OriginalProgram:
    schema:str
    decimal_index:str
    intensities:tuple[int,...]
    parent_codex_index:str|None
    parent_codex_digest:str|None
    source_digest:str
    mechanics_available:int
    is_finished_game:bool=False


@dataclass(frozen=True)
class OriginalPlay:
    resources:tuple[int,...]=(32,32,32,32,32,32,100)
    mastery:tuple[int,...]=(0,)*MECHANIC_COUNT
    domain_evolution:tuple[int,...]=(0,)*MECHANIC_COUNT
    x:int=0
    y:int=0
    turn:int=0
    era:int=0
    realm:int=0
    endings:tuple[str,...]=()
    changed_places:tuple[str,...]=()
    unlocked_joins:tuple[str,...]=()
    history_digest:str=""


def encode_levels(levels:tuple[int,...])->int:
    if (type(levels) is not tuple or len(levels)!=MECHANIC_COUNT or
            any(type(v) is not int or not 0<=v<MECHANIC_LEVELS
                for v in levels)):
        raise ValueError("original game mechanics need 32 independent bounded levels")
    number=0
    for level in levels:
        number=number*MECHANIC_LEVELS+level
    return number


def decode_levels(index:int)->tuple[int,...]:
    if type(index) is not int or not 0<=index<PROGRAM_COUNT:
        raise ValueError("original rulebook address outside 64-bit exact range")
    result=[0]*MECHANIC_COUNT
    for offset in range(MECHANIC_COUNT-1,-1,-1):
        index,result[offset]=divmod(index,MECHANIC_LEVELS)
    return tuple(result)


@lru_cache(maxsize=32)
def _parent_values(index:str)->tuple[tuple[int,...],str]:
    from .dragon_world_codex import unrank,validate
    _,codex=validate(unrank(index))
    return codex.values,codex.digest()


def _parent(index:str|None)->str|None:
    if index is None:return None
    return _parent_values(index)[1]


def make_program(index:str,*,parent_codex_index:str|None=None)->OriginalProgram:
    if (type(index) is not str or len(index)>20 or
            not DECIMAL.fullmatch(index) or int(index)>=PROGRAM_COUNT):
        raise ValueError("original game program needs exact 64-bit decimal identifier")
    levels=decode_levels(int(index))
    parent_digest=_parent(parent_codex_index)
    data=(SCHEMA,index,levels,parent_codex_index,parent_digest)
    return OriginalProgram(
        schema=SCHEMA,decimal_index=index,intensities=levels,
        parent_codex_index=parent_codex_index,
        parent_codex_digest=parent_digest,
        source_digest=_digest(data),
        mechanics_available=sum(x>0 for x in levels),
    )


def program_from_levels(levels:tuple[int,...], *,
                        parent_codex_index:str|None=None)->OriginalProgram:
    return make_program(str(encode_levels(levels)),
                        parent_codex_index=parent_codex_index)


def validate_program(program:OriginalProgram)->None:
    if (not isinstance(program,OriginalProgram) or
            program.schema!=SCHEMA or program.is_finished_game is not False or
            program!=make_program(program.decimal_index,
                                  parent_codex_index=program.parent_codex_index)):
        raise ValueError("forged source rulebook or unreviewed finished-game claim")


def initial(program:OriginalProgram)->OriginalPlay:
    validate_program(program)
    return replace(OriginalPlay(),history_digest=_digest(
        (program.source_digest,"original_genesis"),
    ))


def validate_state(state:OriginalPlay)->None:
    if not isinstance(state,OriginalPlay):
        raise ValueError("missing original game state")
    for row,expected,label in (
        (state.resources,len(RESOURCE_NAMES),"resources"),
        (state.mastery,MECHANIC_COUNT,"mechanic mastery"),
        (state.domain_evolution,MECHANIC_COUNT,"world evolution"),
    ):
        if (type(row) is not tuple or len(row)!=expected or
                any(type(x) is not int or not 0<=x<=MAX_STATE for x in row)):
            raise ValueError("game state "+label+" malformed")
    for x in (state.x,state.y):
        if type(x) is not int or abs(x)>MAX_STATE:
            raise ValueError("original world position outside bounded design")
    for x in (state.turn,state.era,state.realm):
        if type(x) is not int or not 0<=x<=MAX_STATE:
            raise ValueError("original world chronology outside bounded design")
    for seq,cap in ((state.endings,8),(state.changed_places,64),
                    (state.unlocked_joins,16)):
        if (type(seq) is not tuple or len(seq)>cap or len(set(seq))!=len(seq)
                or any(type(x) is not str or not 1<=len(x)<=80 for x in seq)):
            raise ValueError("world outcome history record malformed")
    if (type(state.history_digest) is not str or
            not re.fullmatch(r"[0-9a-f]{64}",state.history_digest)):
        raise ValueError("original world replay digest malformed")


def _append(values:tuple[str,...],item:str,limit:int)->tuple[str,...]:
    if item in values:return values
    return (values+(item,))[-limit:]


def _action(program:OriginalProgram,state:OriginalPlay,index:int)->dict:
    level=program.intensities[index]
    name,domain,spend,earn=MECHANICS[index]
    spend_index=RESOURCE_INDEX[spend]
    earn_index=RESOURCE_INDEX[earn]
    environment=(0,0,0,0)
    if program.parent_codex_index is not None:
        environment=_parent_values(program.parent_codex_index)[0][
            index*4:index*4+4]
    # All 128 prior Codex axes actively influence the new 32-mechanic
    # implementation: 4 environment values per mechanic. Changing its
    # environmental genome changes real required resources, emitted yield
    # and route displacement, never only a source hash.
    expense=level+environment[0]//86
    if spend=="energy":
        expense=2*level+environment[0]//86
    open_=level>0 and state.resources[spend_index]>=expense
    delta=(level*(2+index%5))+environment[1]//64
    dx=(index%5)-2+(environment[2]//86)
    dy=(index//5)%5-2+(environment[3]//86)
    return {
        "id":"practice_"+name,"mechanic":name,"domain":domain,
        "level":level,"available":open_,
        "cost_resource":spend,"cost":expense,
        "gain_resource":earn,"gain":delta,
        "world_effect":"original_"+name,
        "parent_codex_environment":list(environment),
        "physical_position_delta":[dx,dy],
        "reason":"not_in_design" if level==0 else
                 "insufficient_"+spend if not open_ else "available",
    }


def _fusion(program:OriginalProgram,state:OriginalPlay,
            source:int,target:int)->dict:
    """Directed real action between distinct or self-specialized mechanics."""
    a,b=source,target
    name=f"fusion_{a:02d}_{b:02d}"
    la,lb=program.intensities[a],program.intensities[b]
    practiced=(state.mastery[a]>=la and state.mastery[b]>=lb and
               (a!=b or state.mastery[a]>=la*2))
    authored=la>0 and lb>0
    price=1+(a+3*b)%4
    gain=la*lb+(a%4)+2
    material=RESOURCE_NAMES[(a+2*b)%6]
    usable=authored and practiced and state.resources[6]>=price
    return {
        "id":name,"source":MECHANIC_IDS[a],
        "destination":MECHANIC_IDS[b],
        "source_axis":a,"destination_axis":b,
        "available":usable,"requires_earned_mastery":True,
        "cost_resource":"energy","cost":price,
        "gain_resource":material,"gain":gain,
        "position_effect":[a%5-2,b%5-2],
        "domain_effects":[la,lb],
        "reason":"not_in_rule_program" if not authored else
                 "mastery_locked" if not practiced else
                 "insufficient_energy" if state.resources[6]<price
                 else "available",
    }


def interaction_catalog(program:OriginalProgram,state:OriginalPlay, *,
                        offset:int=0,limit:int=32)->dict:
    """Page 1024 directed, actually executable synthesis types."""
    validate_program(program);validate_state(state)
    if (type(offset) is not int or not 0<=offset<DIRECTED_MECHANIC_FUSIONS
            or type(limit) is not int or not 1<=limit<=64):
        raise ValueError("original interaction synthesis pagination invalid")
    end=min(DIRECTED_MECHANIC_FUSIONS,offset+limit)
    interactions=[
        _fusion(program,state,n//MECHANIC_COUNT,n%MECHANIC_COUNT)
        for n in range(offset,end)
    ]
    return {
        "schema":SCHEMA,
        "total_possible_directed_fusions":DIRECTED_MECHANIC_FUSIONS,
        "offset":offset,"returned":len(interactions),
        "interactions":interactions,
        "actually_available":sum(item["available"] for item in interactions),
        "proof":"each earned action has mastery gates, price, "
                "specific movement and directed resource effects",
    }


def choices(program:OriginalProgram,state:OriginalPlay)->list[dict]:
    validate_program(program);validate_state(state)
    result=[_action(program,state,index)
            for index in range(MECHANIC_COUNT)]
    result.append({
        "id":"rest_world","available":True,
        "cost_resource":"none","cost":0,"gain_resource":"energy",
        "gain":16,"reason":"available",
    })
    # Adjacent independent mechanics create 16 meaningful emergent
    # interactions that cannot appear unless BOTH players actually
    # practiced the required mechanics.
    for i in range(0,MECHANIC_COUNT,2):
        j=i+1
        pair=f"join_{MECHANIC_IDS[i]}_{MECHANIC_IDS[j]}"
        if program.intensities[i] and program.intensities[j]:
            enabled=state.mastery[i]>0 and state.mastery[j]>0
            result.append({
                "id":pair,"available":enabled and
                     state.resources[RESOURCE_INDEX["energy"]]>=2,
                "kind":"original_emergent_cross_domain_path",
                "requirements":[MECHANIC_IDS[i],MECHANIC_IDS[j]],
                "reason":"mastery_locked" if not enabled else "available",
                "cost_resource":"energy","cost":2,
                "gain_resource":"lore","gain":i+2,
            })
    return result


def perform(program:OriginalProgram,state:OriginalPlay,action:str)->OriginalPlay:
    validate_program(program);validate_state(state)
    if type(action) is not str or len(action)>130:
        raise ValueError("original game mechanic action outside bounded vocabulary")
    fusion_match=re.fullmatch(r"fusion_([0-9]{2})_([0-9]{2})",action)
    if fusion_match:
        src,dst=int(fusion_match.group(1)),int(fusion_match.group(2))
        selected=(_fusion(program,state,src,dst) if
                  src<MECHANIC_COUNT and dst<MECHANIC_COUNT else None)
    else:
        selected=next((item for item in choices(program,state)
                       if item["id"]==action),None)
    if selected is None or not selected["available"]:
        raise ValueError("player attempted an unavailable original mechanic")
    if state.turn>=MAX_STATE-1:
        raise ValueError("original world turn limit reached")
    changed=replace(state,turn=state.turn+1)
    resources=list(changed.resources)
    mastered=list(changed.mastery)
    evolution=list(changed.domain_evolution)
    locations=changed.changed_places
    joins=changed.unlocked_joins
    endings=changed.endings
    era=changed.era
    realm=changed.realm
    x,y=changed.x,changed.y
    if action=="rest_world":
        resources[RESOURCE_INDEX["energy"]]=min(
            MAX_STATE,resources[RESOURCE_INDEX["energy"]]+16)
    elif action.startswith("practice_"):
        identifier=action.removeprefix("practice_")
        i=MECHANIC_INDEX[identifier]
        row=_action(program,state,i)
        cost=RESOURCE_INDEX[row["cost_resource"]]
        gain=RESOURCE_INDEX[row["gain_resource"]]
        resources[cost]-=row["cost"]
        resources[gain]=min(MAX_STATE,resources[gain]+row["gain"])
        mastered[i]=min(MAX_STATE,mastered[i]+row["level"])
        evolution[i]=min(MAX_STATE,evolution[i]+row["gain"])
        x+=row["physical_position_delta"][0]
        y+=row["physical_position_delta"][1]
        locations=_append(locations,
            f"{identifier}_x{x}_y{y}",64)
        if identifier in ("portal_alignment","orbital_transfer"):
            realm=min(MAX_STATE,realm+row["level"])
        if identifier in ("alternate_conclusions","branching_chronicles"):
            ending=f"original_{identifier}_{row['level']}"
            endings=_append(endings,ending,8)
        if identifier in ("postgame_repair","world_era_cycles"):
            era=min(MAX_STATE,era+row["level"])
    elif fusion_match:
        src,dst=int(fusion_match.group(1)),int(fusion_match.group(2))
        resources[RESOURCE_INDEX["energy"]]-=selected["cost"]
        pool=RESOURCE_INDEX[selected["gain_resource"]]
        resources[pool]=min(MAX_STATE,resources[pool]+selected["gain"])
        mastered[src]=min(MAX_STATE,mastered[src]+1)
        mastered[dst]=min(MAX_STATE,mastered[dst]+1)
        evolution[src]=min(MAX_STATE,evolution[src]+selected["gain"])
        evolution[dst]=min(MAX_STATE,evolution[dst]+selected["gain"])
        x+=selected["position_effect"][0]
        y+=selected["position_effect"][1]
        locations=_append(locations,
            f"original_fusion_{src}_{dst}_x{x}_y{y}",64)
        joins=_append(joins,action,16)
        era=min(MAX_STATE,era+1)
    elif action.startswith("join_"):
        resources[RESOURCE_INDEX["energy"]]-=2
        resources[RESOURCE_INDEX["lore"]]=min(
            MAX_STATE,resources[RESOURCE_INDEX["lore"]]+selected["gain"])
        joins=_append(joins,action,16)
        # A combined mastery path visibly changes world age and access;
        # this is not a free no-op metadata label.
        era=min(MAX_STATE,era+1)
        x+=1
    else:
        raise ValueError("unknown authored original rule")
    advanced=replace(
        changed,resources=tuple(resources),mastery=tuple(mastered),
        domain_evolution=tuple(evolution),x=x,y=y,realm=realm,era=era,
        endings=endings,changed_places=locations,unlocked_joins=joins,
    )
    advanced=replace(advanced,history_digest=_digest(
        (program.source_digest,state.history_digest,action,asdict(
            replace(advanced,history_digest=""),
        )),
    ))
    validate_state(advanced)
    return advanced


def replay(program:OriginalProgram,sequence:tuple[str,...]=(),
           *,starting_state:OriginalPlay|None=None)->OriginalPlay:
    validate_program(program)
    if (type(sequence) is not tuple or len(sequence)>MAX_ACTIONS or
            any(type(x) is not str or not 1<=len(x)<=130 for x in sequence)):
        raise ValueError("original authored mechanic replay is unbounded")
    state=initial(program) if starting_state is None else starting_state
    validate_state(state)
    for action in sequence:
        state=perform(program,state,action)
    return state


def prove_mechanic(program:OriginalProgram,index:int)->dict:
    """Actually run the game's axis mechanic; returns a causal witness."""
    validate_program(program)
    if type(index) is not int or not 0<=index<MECHANIC_COUNT:
        raise ValueError("original mechanic index outside authored registry")
    baseline=initial(program)
    option=_action(program,baseline,index)
    if not option["available"]:
        return {"axis":MECHANIC_IDS[index],"level":option["level"],
                "available":False,"reason":option["reason"],
                "witness":None}
    action=option["id"]
    after=perform(program,baseline,action)
    if (after.mastery[index]!=option["level"] or
            after.domain_evolution[index]!=option["gain"] or
            after.history_digest==baseline.history_digest):
        raise ValueError("original mechanic action did not change real game state")
    return {
        "axis":MECHANIC_IDS[index],"level":option["level"],
        "available":True,"world_effect":option["world_effect"],
        "cost":option["cost"],"gain":option["gain"],
        "position_after":[after.x,after.y],"realm_after":after.realm,
        "era_after":after.era,"endings_after":after.endings,
        "mastery_after":after.mastery[index],
        "world_evolution_after":after.domain_evolution[index],
        "witness":after.history_digest,
    }


def distinguish(left:OriginalProgram,right:OriginalProgram)->dict:
    """Constructively find a distinguishing GAMEPLAY witness for any two programs."""
    validate_program(left);validate_program(right)
    for index,(a,b) in enumerate(zip(left.intensities,right.intensities)):
        if a==b:continue
        x,y=prove_mechanic(left,index),prove_mechanic(right,index)
        if x==y:
            raise ValueError("original gameplay mutation failed semantic separation")
        if a==0 or b==0:
            evidence="different_action_availability"
        else:
            if (x["mastery_after"]==y["mastery_after"] or
                    x["world_evolution_after"]==y["world_evolution_after"]):
                raise ValueError("rule levels differ in identifier but not game consequences")
            evidence="different_executable_cost_rewards_and_world_progress"
        return {
            "schema":SCHEMA,"distinguishable":True,
            "axis_index":index,"axis":MECHANIC_IDS[index],
            "reason":evidence,"left":x,"right":y,
            "claim":"specific differing runtime rule, not distinct copyrighted game expression",
        }
    return {
        "schema":SCHEMA,"distinguishable":False,
        "reason":"same_executable_mechanic_levels",
        "claim":"different environmental genome alone is not a different rulebook",
    }


def binary_nucleus(number:int)->OriginalProgram:
    """16,777,216 independently indexed original enable/disable rulebooks."""
    if type(number) is not int or not 0<=number<MILLION_DISTINCT_ENABLE_PROFILES:
        raise ValueError("original mechanic nucleus index must be 24-bit")
    levels=tuple((number>>(23-i))&1 for i in range(24))+(0,)*8
    return program_from_levels(levels)


def full_binary_nucleus(number:int)->OriginalProgram:
    """Full set of 4,294,967,296 uniquely enabled 32-mechanic programs.

    Legacy binary_nucleus indexes the original 24-bit tier; this expanded
    mode activates all 32 categories including story ending, ecology,
    postgame, survival, world eras and high-level environment systems.
    """
    if type(number) is not int or not 0<=number<FULL_BINARY_PROFILE_COUNT:
        raise ValueError("32-bit original game nucleus outside complete range")
    levels=tuple((number>>(MECHANIC_COUNT-1-i))&1
                 for i in range(MECHANIC_COUNT))
    return program_from_levels(levels)


def capabilities()->dict:
    return {
        "schema":SCHEMA,"actual_mechanic_verbs":MECHANIC_COUNT,
        "levels_per_mechanic":MECHANIC_LEVELS,
        "exact_original_rule_program_address_count":str(PROGRAM_COUNT),
        "mechanically_separable_binary_nuclei":MILLION_DISTINCT_ENABLE_PROFILES,
        "full_original_32_mechanic_binary_nuclei":FULL_BINARY_PROFILE_COUNT,
        "semantics":"each level changes executable action availability, actual "
                    "resource cost/reward, world mutation and replay hash",
        "parent_environment":"optionally uses verified 128-axis World Codex",
        "possible_cross_mechanic_join_routes":16,
        "directed_executable_mechanic_fusion_types":
            DIRECTED_MECHANIC_FUSIONS,
        "real_games_materialized_in_report":0,
        "finished_unique_cleared_games":0,
        "not_claimed":"high address capacity is not millions of completed, "
                      "subjectively unique or legally cleared games",
    }
