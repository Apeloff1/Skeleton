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
EXTENDED_SCHEMA="skeleton.ai.dragon.codex_genome.v3"
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
# Versioned extension: legacy 1024-bit addresses and digests remain byte-for-byte stable.
# These are additional controls, never renames or replacements of the original 128.
EXTENSION_DOMAIN_AXIS={
 "aerial_realms":(
   "sky_islands","cloud_oceans","suspended_archipelagos","skybridge_density",
   "thermal_updrafts","aether_buoyancy","floating_settlements","aerial_isolation",
 ),
 "subterranean":(
   "deep_strata","cavern_ecosystems","magma_tides","underground_rivers",
   "crystal_growth","tectonic_ruptures","fungal_forests","ancient_vaults",
 ),
 "ocean_systems":(
   "coral_cities","abyssal_trenches","kelp_continents","underwater_currents",
   "tidal_megafauna","submarine_ruins","floating_ports","deepwater_pressure",
 ),
 "atmosphere":(
   "jet_streams","wind_shear","supercell_frequency","aurora_cycles",
   "atmospheric_layers","sky_visibility","lightning_density","cloud_ecology",
 ),
 "mobility":(
   "glider_lift","airship_lanes","climbing_networks","vertical_transit",
   "grappling_routes","amphibious_travel","tunnel_networks","fast_travel_cost",
 ),
 "world_population":(
   "npc_population_density","settlement_interdependence","migration_corridors",
   "creature_sociality","civic_conflict","wilderness_encroachment",
   "trade_route_activity","faction_memory_depth",
 ),
 "cinematic":(
   "camera_parallax","horizon_depth","volumetric_lighting","shadow_complexity",
   "atmospheric_perspective","environmental_animation","weather_reactivity",
   "scene_transition_density",
 ),
 "simulation":(
   "ecological_feedback","physical_weather_coupling","construction_integrity",
   "dynamic_path_reconfiguration","terrain_erosion_rate","seasonal_resource_cycle",
   "consequence_persistence","recovery_complexity",
 ),
}
EXTENSION_DOMAINS=tuple(EXTENSION_DOMAIN_AXIS)
EXTENSION_AXIS_NAMES=tuple(axis for group in EXTENSION_DOMAIN_AXIS.values() for axis in group)
EXTENSION_AXIS_INDEX={name:index for index,name in enumerate(EXTENSION_AXIS_NAMES)}
ALL_DOMAINS=DOMAINS+EXTENSION_DOMAINS
ALL_AXIS_NAMES=AXIS_NAMES+EXTENSION_AXIS_NAMES
assert len(EXTENSION_DOMAINS)==8 and len(EXTENSION_AXIS_NAMES)==64
assert len(set(ALL_AXIS_NAMES))==192 and all(len(v)==8 for v in EXTENSION_DOMAIN_AXIS.values())
AXES_PER_DOMAIN=8
AXIS_LEVELS=256
CODEX_GENOMES=AXIS_LEVELS**len(AXIS_NAMES)   # 2**1024
CODEX_WORLD_ADDRESSES=GENOMIC_WORLD_COUNT*CODEX_GENOMES  # immutable v2 address range
EXTENSION_GENOMES=AXIS_LEVELS**len(EXTENSION_AXIS_NAMES)
EXTENDED_CODEX_WORLD_ADDRESSES=CODEX_WORLD_ADDRESSES*EXTENSION_GENOMES
MAX_DIGITS=len(str(EXTENDED_CODEX_WORLD_ADDRESSES))
DECIMAL=re.compile(r"(0|[1-9][0-9]*)\Z")

@dataclass(frozen=True)
class WorldCodex:
    values:tuple[int,...]
    extension_values:tuple[int,...]=(0,)*64

    def __post_init__(self):
        if (type(self.values) is not tuple or len(self.values)!=128 or
                any(type(x) is not int or not 0<=x<=255 for x in self.values)):
            raise ValueError("world codex expects 128 bounded 8-bit simulation values")
        if (type(self.extension_values) is not tuple or len(self.extension_values)!=64 or
                any(type(x) is not int or not 0<=x<=255 for x in self.extension_values)):
            raise ValueError("world extension requires 64 bounded 8-bit simulation values")

    def level(self,name:str)->int:
        if type(name) is not str:
            raise ValueError("unrecognized world design axis")
        if name in AXIS_INDEX:return self.values[AXIS_INDEX[name]]
        if name in EXTENSION_AXIS_INDEX:
            return self.extension_values[EXTENSION_AXIS_INDEX[name]]
        raise ValueError("unrecognized world design axis")

    def domain(self,domain:str)->tuple[int,...]:
        if domain in DOMAIN_INDEX:
            first=DOMAIN_INDEX[domain]*8
            return self.values[first:first+8]
        if domain in EXTENSION_DOMAIN_AXIS:
            first=EXTENSION_DOMAINS.index(domain)*8
            return self.extension_values[first:first+8]
        raise ValueError("unknown authored original game world domain")

    def digest(self)->str:
        if not any(self.extension_values):
            return _sha(["dragon_world_codex_v2",self.values])
        return _sha(["dragon_world_codex_v3",self.values,self.extension_values])


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
    extension_values:tuple[int,...]=(0,)*64


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
    if n>=EXTENDED_CODEX_WORLD_ADDRESSES:
        raise ValueError("world codex index out of exact range")
    return n


def unrank(index:str)->CodexAddress:
    n=read_index(index)
    extension_index,legacy_index=divmod(n,CODEX_WORLD_ADDRESSES)
    parent,code=divmod(legacy_index,CODEX_GENOMES)
    root=unrank_genome_address(str(parent))
    genome=decode(code)
    extension_values=tuple(extension_index.to_bytes(64,"big"))
    extended=extension_index!=0
    schema=EXTENDED_SCHEMA if extended else SCHEMA
    return CodexAddress(
        schema=schema,decimal_index=index,
        parent_decimal_index=str(parent),
        parent_genome_digest=root.genome_digest,
        codex_decimal=str(code),values=genome.values,
        codex_digest=(
            _sha([EXTENDED_SCHEMA,root.genome_digest,genome.values,extension_values])
            if extended else _sha([SCHEMA,root.genome_digest,genome.values])
        ),
        original_work_only=True,unique_published_game=False,
        extension_values=extension_values,
    )


def rank(parent_decimal_index:str,genome:WorldCodex)->str:
    parent=unrank_genome_address(parent_decimal_index)
    legacy=int(parent.decimal_index)*CODEX_GENOMES+encode(genome)
    extension=int.from_bytes(bytes(genome.extension_values),"big")
    return str(legacy+extension*CODEX_WORLD_ADDRESSES)


def edit(index:str,updates:dict[str,int])->CodexAddress:
    old=unrank(index)
    if (type(updates) is not dict or len(updates)>len(ALL_AXIS_NAMES) or
            any(type(k) is not str or k not in set(ALL_AXIS_NAMES) or
                type(v) is not int or not 0<=v<=255
                for k,v in updates.items())):
        raise ValueError("invalid or unimplemented game-world codex settings")
    change=list(old.values)
    extension=list(old.extension_values)
    for axis,level in updates.items():
        if axis in AXIS_INDEX:change[AXIS_INDEX[axis]]=level
        else:extension[EXTENSION_AXIS_INDEX[axis]]=level
    return unrank(rank(old.parent_decimal_index,WorldCodex(tuple(change),tuple(extension))))


def validate(address:CodexAddress)->tuple[WorldGenomeAddress,WorldCodex]:
    if (not isinstance(address,CodexAddress) or
            address!=unrank(address.decimal_index)):
        raise ValueError("source world codex address has been forged")
    return unrank_genome_address(address.parent_decimal_index),WorldCodex(
        address.values,address.extension_values)


def summary()->dict:
    return {
        "schema":SCHEMA,
        "domains":len(ALL_DOMAINS),
        "axes":len(ALL_AXIS_NAMES),
        "legacy_domains":len(DOMAINS),"legacy_axes":len(AXIS_NAMES),
        "extension_schema":EXTENDED_SCHEMA,
        "extension_domains":len(EXTENSION_DOMAINS),
        "extension_axes":len(EXTENSION_AXIS_NAMES),
        "levels_per_axis":AXIS_LEVELS,
        "grouped_axes":{**{k:list(v) for k,v in DOMAIN_AXIS.items()},
                        **{k:list(v) for k,v in EXTENSION_DOMAIN_AXIS.items()}},
        "new_genomic_combinations_per_existing_world":str(CODEX_GENOMES),
        "legacy_exact_reversible_original_world_addresses":str(CODEX_WORLD_ADDRESSES),
        "total_exact_reversible_original_world_addresses":str(EXTENDED_CODEX_WORLD_ADDRESSES),
        "extension_combinations_per_legacy_address":str(EXTENSION_GENOMES),
        "compatibility":"legacy addresses, v2 digests and base 128 axis order unchanged",
        "maximum_decimal_digits":MAX_DIGITS,
        "encoding":"strict canonical decimal, arbitrary precision Python integer",
        "enumerated_games":0,"independently_reviewed_unique_games":0,
        "status":"only individually requested designs are generated and simulated",
    }
