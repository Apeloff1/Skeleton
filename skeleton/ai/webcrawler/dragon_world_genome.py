"""Reversible, meaning-bearing world genomes in an enormous lazy design lattice.

An address chooses one existing valid world/style/lifecycle plus 24 explicit
16-level original simulation controls. Every axis is independently editable
and appears as a concrete numeric setting in observed world generation.
No billion-world enumeration, no counting aliases as legally unique games.

Big indexes are always DECIMAL STRINGS at API/UI boundaries. JS numeric
values above 2**53 must not be used for these identities.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
import re

from .dragon_living_world import create_world,LivingWorld,_sha
from .dragon_living_world_lattice import (
    DESIGN_ADDRESS_COUNT,unrank_design,rank_design,
)

SCHEMA="skeleton.ai.dragon.genomic_world_lattice.v1"
DIGIT_BASE=16
AXIS_NAMES=(
    "terrain_elevation",
    "biome_mosaic",
    "watershed",
    "cavern_density",
    "sky_islands",
    "weather_violence",
    "season_clock",
    "day_cycle",
    "flora_dynamics",
    "fauna_aggression",
    "food_bounty",
    "mineral_density",
    "building_complexity",
    "settlement_growth",
    "market_cycle",
    "diplomacy_tension",
    "hostile_pressure",
    "traversal_drag",
    "shifting_maze_rate",
    "portal_instability",
    "discovery_rarity",
    "research_depth",
    "narrative_choice_impact",
    "postgame_renewal",
)
AXIS_DOMAINS=(
    "elevation contours and hill traversal",
    "original biome composition and local mosaic",
    "wetlands, flooding and water supplies",
    "cave occurrence, mining and darkness",
    "sky terrain and elevated traversal",
    "rain and storm exposure",
    "calendar and seasonal progression",
    "light cycle and night travel",
    "plant growth, restoration and recovery",
    "wildlife pressure and ecosystem observation",
    "gatherable food in a region",
    "mineral supply and extraction difficulty",
    "wood and ore construction requirements",
    "settlement yield and persistence",
    "resource pricing and trade opportunity",
    "faction negotiation and social tension",
    "hostility and expedition exposure",
    "movement time, effort and wayfinding",
    "changing corridors and maze wait pressure",
    "realm transfer friction and gateway signal",
    "discovery rewards and rarity",
    "science progress and analysis",
    "narrative alignment and choice consequences",
    "post-ending regeneration and world rebuilding",
)
assert len(AXIS_NAMES)==24==len(AXIS_DOMAINS)
assert len(set(AXIS_NAMES))==24
GENOME_VARIATIONS=DIGIT_BASE**len(AXIS_NAMES)   # 2**96, exact integer
GENOMIC_WORLD_COUNT=DESIGN_ADDRESS_COUNT*GENOME_VARIATIONS
MAX_DECIMAL_DIGITS=len(str(GENOMIC_WORLD_COUNT))
assert GENOMIC_WORLD_COUNT>=10**18
DECIMAL=re.compile(r"(0|[1-9][0-9]*)\Z")

@dataclass(frozen=True)
class Genome:
    levels:tuple[int,...]

    def __post_init__(self):
        if (type(self.levels) is not tuple or
                len(self.levels)!=len(AXIS_NAMES) or
                any(type(n) is not int or not 0<=n<16 for n in self.levels)):
            raise ValueError("world genome requires exactly 24 typed 4-bit physical controls")

    def get(self,name:str)->int:
        try:index=AXIS_NAMES.index(name)
        except ValueError as exc:raise ValueError("unknown world simulation axis") from exc
        return self.levels[index]

    def effects(self)->dict:
        # Every selected axis affects a named domain. Actual environmental
        # and gameplay use is implemented by dragon_genomic_world.py.
        return {name:{"level":n,"strength":n+1,"domain":AXIS_DOMAINS[i]}
                for i,(name,n) in enumerate(zip(AXIS_NAMES,self.levels))}


@dataclass(frozen=True)
class WorldGenomeAddress:
    schema:str
    decimal_index:str
    base_design_index:int
    genomic_code:str
    world_id:int
    variant:int
    style:str
    lifecycle:str
    levels:tuple[int,...]
    base_world_fingerprint:str
    genome_digest:str
    actual_game_configuration:bool
    completed_unique_game:bool


def genome_code(genome:Genome)->int:
    if not isinstance(genome,Genome):
        raise ValueError("original world requires typed 24-axis genome")
    n=0
    for value in genome.levels:n=(n<<4)|value
    return n


def genome_from_code(n:int)->Genome:
    if type(n) is not int or not 0<=n<GENOME_VARIATIONS:
        raise ValueError("genome index must fit 96 actual axis bits")
    values=[0]*len(AXIS_NAMES)
    for i in range(len(values)-1,-1,-1):
        values[i]=n&15
        n>>=4
    if n:raise ValueError("genome identifier has unclaimed high bits")
    return Genome(tuple(values))


def integer_address(value:str)->int:
    if (type(value) is not str or not 1<=len(value)<=MAX_DECIMAL_DIGITS
        or not DECIMAL.fullmatch(value)):
        raise ValueError("world identifier must be a canonical decimal string")
    number=int(value)
    if number>=GENOMIC_WORLD_COUNT:
        raise ValueError("world identifier exceeds exact compositional capacity")
    return number


def unrank_genome_address(decimal_index:str)->WorldGenomeAddress:
    index=integer_address(decimal_index)
    old_code,genes=divmod(index,GENOME_VARIATIONS)
    base=unrank_design(old_code)
    genome=genome_from_code(genes)
    return WorldGenomeAddress(
        schema=SCHEMA,decimal_index=decimal_index,
        base_design_index=old_code,genomic_code=str(genes),
        world_id=base.world_id,variant=base.variation,
        style=base.style,lifecycle=base.lifecycle,
        levels=genome.levels,
        base_world_fingerprint=base.original_world_fingerprint,
        genome_digest=_sha([SCHEMA,old_code,genes,
                            base.original_world_fingerprint]),
        actual_game_configuration=True,completed_unique_game=False,
    )


def rank_genome_address(world:LivingWorld,genome:Genome)->str:
    return str(rank_design(world)*GENOME_VARIATIONS+genome_code(genome))


def edit_genome(index:str,changes:dict[str,int])->WorldGenomeAddress:
    original=unrank_genome_address(index)
    if type(changes) is not dict or len(changes)>len(AXIS_NAMES):
        raise ValueError("world genome edit must be bounded named simulation axes")
    updated=list(original.levels)
    for name,level in changes.items():
        if type(name) is not str or name not in AXIS_NAMES or (
            type(level) is not int or not 0<=level<=15):
            raise ValueError("invalid physical world generation control")
        updated[AXIS_NAMES.index(name)]=level
    return unrank_genome_address(
        str(original.base_design_index*GENOME_VARIATIONS+
            genome_code(Genome(tuple(updated)))))


def genome_world(address:WorldGenomeAddress)->tuple[LivingWorld,Genome]:
    if not isinstance(address,WorldGenomeAddress) or address.schema!=SCHEMA:
        raise ValueError("unknown authored original world genome")
    canonical=unrank_genome_address(address.decimal_index)
    if canonical!=address:
        raise ValueError("original world genome/source evidence is inconsistent")
    world=create_world(world_id=address.world_id,variant=address.variant,
                       style=address.style,lifecycle=address.lifecycle)
    if world.world_fingerprint!=address.base_world_fingerprint:
        raise ValueError("underlying game world rules changed")
    return world,Genome(address.levels)


def lattice_summary()->dict:
    return {
        "schema":SCHEMA,
        "controlled_simulation_axes":len(AXIS_NAMES),
        "levels_per_axis":DIGIT_BASE,
        "axes":[{"id":name,"description":AXIS_DOMAINS[i],
                 "levels":16} for i,name in enumerate(AXIS_NAMES)],
        "genomes_per_original_base_design":str(GENOME_VARIATIONS),
        "valid_original_base_world_profiles":str(DESIGN_ADDRESS_COUNT),
        "reversibly_addressable_world_configurations":str(GENOMIC_WORLD_COUNT),
        "minimum_requested_quintillion":"1000000000000000000",
        "address_encoding":"canonical arbitrary-precision decimal string",
        "worlds_enumerated_for_this_report":0,
        "completed_or_legally_cleared_games":0,
        "note":"Exact index capacity, not proof of unique games or that all "
               "configurations have been materialized, reviewed or played.",
    }
