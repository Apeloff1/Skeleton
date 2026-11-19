"""Dragon World Codex v2 — 128 independent 256-level authored controls.

Every axis is named for a concrete world property. This augments rather than
silently changes the existing 24x16 genome schema. Encoding is a lossless
1024-bit integer (128 bytes) paired with the previous, fully addressable
genomic design. No random generator collision is counted as unique authored
content; identity is reversible across the full address range.

These axes model original environmental, cultural, temporal and narrative
processes inspired by broad genre *concepts*, not copied maps, characters,
scripts, scenes, illustrations, trademarks, film dialogue or game assets.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from .dragon_world_genome import (
    GENOMIC_WORLD_COUNT,unrank_genome_address,WorldGenomeAddress,
)
from .dragon_living_world import _sha

SCHEMA="skeleton.ai.dragon.codex_genome.v2"
DOMAIN_AXIS={
 "geology":(
   "elevation_tectonics","plate_migration","karst_depth",
   "volcanic_activity","erosion_clock","mineral_layers",
   "gravity_variation","substrate_stability",
 ),
 "hydrology":(
   "ocean_depth","tide_clock","river_flux","groundwater_reserve",
   "flood_recurrence","ice_thickness","current_velocity","water_purity",
 ),
 "climate":(
   "storm_fronts","rain_seasons","prevailing_wind","solar_radiance",
   "snow_cover","temperature_extremes","fog_density","atmospheric_pressure",
 ),
 "ecology":(
   "flora_succession","fauna_migration","predator_pressure",
   "pollination_cycles","disease_ecology","ecosystem_recovery",
   "resource_regrowth","habitat_fragmentation",
 ),
 "settlements":(
   "urban_density","settlement_decay","reconstruction_rate","housing_pressure",
   "transport_infrastructure","public_services","food_security","migration_pressure",
 ),
 "factions":(
   "trust_dynamics","diplomatic_friction","territory_claims",
   "reputation_decay","alliance_threshold","espionage_risk",
   "social_mobility","regional_autonomy",
 ),
 "economy":(
   "trade_volatility","material_scarcity","barter_complexity",
   "supply_chain_resilience","transport_tariffs","crafting_yield",
   "labor_specialization","black_market_pressure",
 ),
 "technology":(
   "research_cost","engineering_maturity","power_network_capacity",
   "automation_density","signal_transmission","repair_complexity",
   "manufacturing_efficiency","discovery_diffusion",
 ),
 "arcana":(
   "ritual_maturity","aether_flow","portal_alignment",
   "spell_fatigue","enchantment_decay","leyline_turbulence",
   "countermagic_field","dream_access",
 ),
 "cosmology":(
   "orbit_period","celestial_alignment","radiation_flux",
   "stellar_distance","spaceflight_infrastructure","time_dilation",
   "dimensional_stability","extraterrestrial_contact",
 ),
 "narrative":(
   "choice_permanence","story_branching","moral_ambiguity",
   "revelation_delay","memory_reliability","ending_multiplicity",
   "companion_loyalty","unreliable_history",
 ),
 "chronology":(
   "era_length","historical_drift","seasonal_ageing","future_visibility",
   "past_access","temporal_anomaly","world_reset_persistence",
   "generation_turnover",
 ),
 "topology":(
   "maze_mutation_frequency","corridor_rotation","one_way_frequency",
   "secret_density","doubleback_weight","scenic_complexity",
   "verticality","world_seam_complexity",
 ),
 "traversal":(
   "ground_friction","water_navigation_cost","aerial_visibility",
   "rail_intervals","airship_reliability","caravan_risk",
   "vehicle_fuel_use","shortcut_stability",
 ),
 "access":(
   "skill_gate_depth","equipment_gate_depth","social_permission",
   "time_window_strictness","weather_access_strictness",
   "resource_gate_depth","knowledge_gate_depth","multi_stage_unlock",
 ),
 "postgame":(
   "world_repopulation","aftermath_repair","new_game_plus_inheritance",
   "alternate_ending_access","post_story_expansion",
   "dynasty_persistence","ecological_legacy","persistent_world_scars",
 ),
}
DOMAINS=tuple(DOMAIN_AXIS)
AXIS_NAMES=tuple(axis for domain in DOMAINS for axis in DOMAIN_AXIS[domain])
AXIS_INDEX={name:n for n,name in enumerate(AXIS_NAMES)}
DOMAIN_INDEX={name:n for n,name in enumerate(DOMAINS)}
assert len(DOMAINS)==16 and len(AXIS_NAMES)==128
assert len(AXIS_INDEX)==128 and all(len(axes)==8 for axes in DOMAIN_AXIS.values())
AXES_PER_DOMAIN=8
AXIS_LEVELS=256
CODEX_GENOMES=AXIS_LEVELS**len(AXIS_NAMES)   # 2**1024
CODEX_WORLD_ADDRESSES=GENOMIC_WORLD_COUNT*CODEX_GENOMES
MAX_DIGITS=len(str(CODEX_WORLD_ADDRESSES))
DECIMAL=re.compile(r"(0|[1-9][0-9]*)\Z")

@dataclass(frozen=True)
class WorldCodex:
    values:tuple[int,...]

    def __post_init__(self):
        if (type(self.values) is not tuple or len(self.values)!=128 or
                any(type(x) is not int or not 0<=x<=255 for x in self.values)):
            raise ValueError("world codex expects 128 bounded 8-bit simulation values")

    def level(self,name:str)->int:
        try:return self.values[AXIS_INDEX[name]]
        except (KeyError,TypeError) as exc:
            raise ValueError("unrecognized world design axis") from exc

    def domain(self,domain:str)->tuple[int,...]:
        if domain not in DOMAIN_INDEX:
            raise ValueError("unknown authored original game world domain")
        first=DOMAIN_INDEX[domain]*8
        return self.values[first:first+8]

    def digest(self)->str:
        return _sha(["dragon_world_codex_v2",self.values])


@dataclass(frozen=True)
class CodexAddress:
    schema:str
    decimal_index:str
    parent_decimal_index:str
    parent_genome_digest:str
    codex_decimal:str
    values:tuple[int,...]
    codex_digest:str
    original_work_only:bool
    unique_published_game:bool


def encode(codex:WorldCodex)->int:
    if not isinstance(codex,WorldCodex):
        raise ValueError("codex must be typed")
    return int.from_bytes(bytes(codex.values),"big")


def decode(code:int)->WorldCodex:
    if type(code) is not int or not 0<=code<CODEX_GENOMES:
        raise ValueError("world codex 1024-bit integer exceeded")
    return WorldCodex(tuple(code.to_bytes(128,"big")))


def read_index(index:str)->int:
    if (type(index) is not str or not 1<=len(index)<=MAX_DIGITS
            or not DECIMAL.fullmatch(index)):
        raise ValueError("world codex address must be exact decimal string")
    n=int(index)
    if n>=CODEX_WORLD_ADDRESSES:
        raise ValueError("world codex index out of exact range")
    return n


def unrank(index:str)->CodexAddress:
    n=read_index(index)
    parent,code=divmod(n,CODEX_GENOMES)
    root=unrank_genome_address(str(parent))
    genome=decode(code)
    return CodexAddress(
        schema=SCHEMA,decimal_index=index,
        parent_decimal_index=str(parent),
        parent_genome_digest=root.genome_digest,
        codex_decimal=str(code),values=genome.values,
        codex_digest=_sha([SCHEMA,root.genome_digest,genome.values]),
        original_work_only=True,unique_published_game=False,
    )


def rank(parent_decimal_index:str,genome:WorldCodex)->str:
    parent=unrank_genome_address(parent_decimal_index)
    return str(int(parent.decimal_index)*CODEX_GENOMES+encode(genome))


def edit(index:str,updates:dict[str,int])->CodexAddress:
    old=unrank(index)
    if (type(updates) is not dict or len(updates)>128 or
            any(type(k) is not str or k not in AXIS_INDEX or
                type(v) is not int or not 0<=v<=255
                for k,v in updates.items())):
        raise ValueError("invalid or unimplemented game-world codex settings")
    change=list(old.values)
    for axis,level in updates.items():change[AXIS_INDEX[axis]]=level
    return unrank(rank(old.parent_decimal_index,WorldCodex(tuple(change))))


def validate(address:CodexAddress)->tuple[WorldGenomeAddress,WorldCodex]:
    if (not isinstance(address,CodexAddress) or address.schema!=SCHEMA or
            address!=unrank(address.decimal_index)):
        raise ValueError("source world codex address has been forged")
    return unrank_genome_address(address.parent_decimal_index),WorldCodex(address.values)


def summary()->dict:
    return {
        "schema":SCHEMA,
        "domains":len(DOMAINS),
        "axes":len(AXIS_NAMES),
        "levels_per_axis":AXIS_LEVELS,
        "grouped_axes":{k:list(v) for k,v in DOMAIN_AXIS.items()},
        "new_genomic_combinations_per_existing_world":str(CODEX_GENOMES),
        "total_exact_reversible_original_world_addresses":str(CODEX_WORLD_ADDRESSES),
        "maximum_decimal_digits":MAX_DIGITS,
        "encoding":"strict canonical decimal, arbitrary precision Python integer",
        "enumerated_games":0,"independently_reviewed_unique_games":0,
        "status":"only individually requested designs are generated and simulated",
    }
