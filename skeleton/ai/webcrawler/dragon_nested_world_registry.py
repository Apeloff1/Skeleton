"""Original cross-era realm families, with explicit *implemented* mechanics.

Inspired by high-level design principles from classic parallel-world, item-depth,
procedurally reconfigured, alternate-physics and world-within-world games. All
names, transitions, palettes and rule data are newly authored for Dragon;
no proprietary stories, characters, level maps, ROMs or assets are copied.

The registry deliberately distinguishes mechanics backed by executable runtime
semantics from a source-level creative vocabulary. A category name is never
evidence of platform hardware, complete 3D physics or authored levels.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import re

SCHEMA="skeleton.ai.dragon.original_nested_realm_families.v1"
TRANSFORMS=(
    "identity","shadow","light","mirror_x","mirror_y","inversion","reverse",
    "spectral","submerged","buoyant","low_gravity","high_gravity","storm",
    "heat","cold","dream","time_shift","miniature","colossal","celestial",
    "void","rotating","fractured","fungal","verdant","mechanical",
    "crystalline","stratified","echo","astral","phase_shift",
    "isometric","orbiting","branching","recursive","upside_down",
)
ENTRY_MODES=(
    "gate","portal","mirror","reflection","dream","ritual","craft",
    "descent","ascend","elevator","vehicle","passage","summoning",
    "tide","starship","threshold","memory","item","rift","shuttle",
)
TRAVERSAL=(
    "walk","swim","float","fly","sail","climb","crawl","glide",
    "portal","jump","ride","teleport","swing","dig","orbit",
    "phase","scale","reverse_walk","echo_step","drift","slide",
)
CONSEQUENCES=(
    "none","collect_knowledge","upgrade_item","affect_parent",
    "change_faction","alter_weather","earn_key","awaken_ecology",
    "unlock_stage","rewrite_shortcut","advance_story",
)
TONE=(
    "luminous","somber","awe","whimsical","haunting","lush",
    "undersea","mythic","cosmic","serene","ominous","wonder",
    "mysterious","epic","gentle","wild","ancient",
)
BIOME_CLASSES=(
    "rainforest","giant_canopy","alpine_forest","fern_vale","mossy_ruins",
    "mangrove","floodplain","lily_lagoon","coral_garden","abyssal_reef",
    "kelp_forest","glacial_shelf","crystal_ridge","amber_steppe",
    "volcanic_isles","floating_meadows","moonlit_grove","twilight_orchard",
    "starlit_desert","sunrise_valley","dusk_ravine","cavern_city",
    "subterranean_river","fungal_canopy","spiral_tower","stone_labyrinth",
    "mirror_lake","glass_city","clockwork_basin","celestial_isles",
    "ancient_skybridge","orbital_habitat","starfield","gas_giant_clouds",
    "asteroid_garden","mythic_valley","ghost_forest","dream_marsh",
    "shadow_citadel","bright_sanctuary","forgotten_library",
    "miniature_garden","colossal_gorge","reversed_castle","salt_flats",
    "whispering_fields","planetary_canyon","outer_void","sunken_palace",
    "luminous_wetlands","aurora_coast","impossible_archipelago",
    "river_delta","prairie_sky","thunder_plateau","redwood_cathedral",
    "floating_reef","fractured_mesa","bronze_terraces","dust_sea",
    "gravity_rift","ecological_dome","storm_summit","cloud_kingdom",
)
FOLIAGE_TYPES=(
    "fern","moss","orchid","liana","lily","mangrove","redwood",
    "palm","vine","reed","kelp","coral","algae","lichen",
    "canopy","bloom","mycelium","crystal_flower","stargrass",
    "luminous_spore","sky_ivy","ice_blossom","thunder_root",
    "amber_leaves","ghost_petals","sunflowers","wild_berries",
    "river_grass","ancient_seeds","floating_pollen","white_bark",
    "silver_blossom","sea_fan","needle_pine",
)
ATMOSPHERE_LAYERS=(
    "near_fog","distance_haze","volumetric_shafts","rain_curtain",
    "snow_drift","floating_spores","motes","fireflies","aurora",
    "low_cloud","high_cloud","moon_glow","sun_rays","embers",
    "spray","ripples","caustic_light","water_surface","wind_streaks",
    "luminous_dust","starlight","pollen","heat_haze","mist",
    "lightning","shadow_silhouette","planetshine","orbital_rim",
    "coral_particles","magic_motes","leaf_swirl","turbulent_air",
)
PALETTE_NAMES=(
    "jade_dawn","deep_emerald","amber_fog","copper_sunset",
    "violet_twilight","pearl_moon","azure_current","pale_coral",
    "midnight_blue","abyssal_teal","golden_forest","wild_rose",
    "stellar_indigo","nebula_rose","prismatic_dream","frost_silver",
    "lava_glow","silver_mirror","moss_and_stone","cobalt_echo",
    "antique_parchment","glass_cyan","charcoal_fog","luminous_verdant",
    "sunlit_marsh","low_poly_pastel","retro_forest","retro_ocean",
    "dark_noir","high_contrast_dusk","cloud_white","mythic_gold",
)
SAFE=re.compile(r"[a-z][a-z0-9_]{1,47}\Z")

# Distinct original realm purposes. Each profile is one typed set of
# mechanics; runtime actions (enter, interact, exit, echo...) implement them.
# Cross product with tones/palettes/biomes is lazy and deterministic.
RAW_FAMILIES=(
    ("shadow_canopy","shadow","portal","walk","collect_knowledge","haunting"),
    ("sunlit_canopy","light","passage","walk","awaken_ecology","luminous"),
    ("mirrored_wilds","mirror_x","mirror","reverse_walk","rewrite_shortcut","mysterious"),
    ("reflected_spires","mirror_y","reflection","walk","earn_key","awe"),
    ("inverted_forest","inversion","rift","reverse_walk","unlock_stage","wonder"),
    ("reverse_citadel","reverse","passage","reverse_walk","unlock_stage","epic"),
    ("upturned_tower","upside_down","elevator","climb","earn_key","wonder"),
    ("spectral_wood","spectral","rift","phase","collect_knowledge","haunting"),
    ("ancestral_mist","echo","memory","echo_step","advance_story","ancient"),
    ("luminous_depths","submerged","descent","swim","collect_knowledge","awe"),
    ("abyssal_garden","submerged","tide","swim","affect_parent","mysterious"),
    ("coral_cathedral","submerged","passage","swim","awaken_ecology","serene"),
    ("floating_river","buoyant","portal","float","alter_weather","wonder"),
    ("wind_palace","storm","ascend","glide","earn_key","wild"),
    ("skyroot_isles","low_gravity","ascend","float","collect_knowledge","lush"),
    ("dense_core","high_gravity","descent","climb","upgrade_item","ominous"),
    ("ember_atolls","heat","vehicle","sail","earn_key","epic"),
    ("frost_hollows","cold","rift","slide","collect_knowledge","serene"),
    ("crystal_chambers","crystalline","passage","walk","upgrade_item","awe"),
    ("moonlit_garden","light","gate","walk","awaken_ecology","serene"),
    ("eclipsed_orchard","shadow","gate","walk","affect_parent","somber"),
    ("dream_libraries","dream","dream","echo_step","collect_knowledge","mysterious"),
    ("memory_valley","time_shift","memory","walk","advance_story","ancient"),
    ("yesterday_estuary","time_shift","threshold","sail","alter_weather","mysterious"),
    ("tomorrow_meadow","time_shift","threshold","walk","unlock_stage","wonder"),
    ("miniature_kingdom","miniature","item","scale","upgrade_item","whimsical"),
    ("jewel_interior","miniature","item","walk","upgrade_item","awe"),
    ("artifact_archive","miniature","item","crawl","collect_knowledge","ancient"),
    ("gigantic_grove","colossal","gate","climb","collect_knowledge","epic"),
    ("ancient_titan_halls","colossal","elevator","walk","earn_key","epic"),
    ("starfield_sanctuary","astral","starship","orbit","advance_story","cosmic"),
    ("orbiting_monastery","orbiting","shuttle","orbit","collect_knowledge","serene"),
    ("celestial_isles","celestial","ascend","fly","earn_key","awe"),
    ("meteor_garden","celestial","starship","walk","awaken_ecology","cosmic"),
    ("solar_arch","light","gate","walk","alter_weather","luminous"),
    ("lunar_reef","spectral","shuttle","float","collect_knowledge","cosmic"),
    ("constellation_bridge","celestial","rift","phase","earn_key","awe"),
    ("night_void","void","rift","drift","rewrite_shortcut","ominous"),
    ("phase_bazaar","phase_shift","threshold","phase","change_faction","whimsical"),
    ("portal_nexus","branching","portal","teleport","rewrite_shortcut","epic"),
    ("many_gate_ring","rotating","gate","teleport","earn_key","mysterious"),
    ("recursive_cavern","recursive","descent","crawl","unlock_stage","ominous"),
    ("spiral_underworld","rotating","descent","walk","collect_knowledge","mysterious"),
    ("labyrinth_nursery","branching","gate","walk","awaken_ecology","lush"),
    ("fractal_ruins","fractured","rift","jump","earn_key","ancient"),
    ("shardbound_dunes","fractured","vehicle","ride","affect_parent","wild"),
    ("thunder_temples","storm","ritual","climb","alter_weather","epic"),
    ("wind_carved_world","storm","passage","glide","collect_knowledge","awe"),
    ("verdant_chorus","verdant","summoning","walk","awaken_ecology","lush"),
    ("fungal_symphony","fungal","passage","crawl","collect_knowledge","mysterious"),
    ("clockwork_ocean","mechanical","vehicle","sail","upgrade_item","wonder"),
    ("ironwood_machine","mechanical","craft","walk","upgrade_item","epic"),
    ("ghostlight_passage","spectral","rift","phase","earn_key","haunting"),
    ("whisper_kingdom","echo","memory","echo_step","advance_story","mythic"),
    ("mythic_fells","identity","ritual","walk","advance_story","mythic"),
    ("faerie_lanterns","dream","ritual","float","collect_knowledge","whimsical"),
    ("ancient_epic_realm","identity","gate","walk","advance_story","epic"),
    ("storybook_wilds","isometric","passage","jump","awaken_ecology","whimsical"),
    ("painted_pastures","identity","portal","walk","collect_knowledge","whimsical"),
    ("isometric_bastion","isometric","elevator","climb","unlock_stage","epic"),
    ("strata_of_stars","stratified","starship","orbit","earn_key","cosmic"),
    ("planetary_frontier","stratified","starship","ride","awaken_ecology","epic"),
    ("ocean_planet","submerged","starship","swim","collect_knowledge","cosmic"),
    ("forest_planet","verdant","starship","walk","affect_parent","lush"),
    ("desert_planet","heat","starship","ride","collect_knowledge","awe"),
    ("floating_planet","low_gravity","shuttle","float","earn_key","wonder"),
    ("tidal_moon","submerged","shuttle","sail","alter_weather","cosmic"),
    ("gas_giant_drift","buoyant","starship","drift","collect_knowledge","awe"),
    ("ringed_world","orbiting","starship","orbit","earn_key","cosmic"),
    ("stellar_cluster","celestial","starship","orbit","advance_story","epic"),
    ("spiral_universe","recursive","starship","orbit","collect_knowledge","cosmic"),
    ("outer_continuum","void","rift","phase","unlock_stage","mysterious"),
    ("primordial_flame","heat","ritual","walk","alter_weather","mythic"),
    ("primordial_tide","submerged","ritual","swim","alter_weather","mythic"),
    ("primordial_air","buoyant","ritual","fly","alter_weather","mythic"),
    ("primordial_earth","stratified","ritual","dig","affect_parent","mythic"),
    ("primordial_light","light","ritual","walk","collect_knowledge","luminous"),
    ("primordial_shadow","shadow","ritual","phase","collect_knowledge","somber"),
    ("elemental_storm","storm","rift","glide","alter_weather","epic"),
    ("elemental_ice","cold","rift","walk","alter_weather","serene"),
    ("elemental_moss","verdant","passage","walk","awaken_ecology","lush"),
    ("elemental_crystal","crystalline","gate","walk","upgrade_item","awe"),
    ("elemental_clock","time_shift","elevator","walk","unlock_stage","wonder"),
    ("boundary_between","phase_shift","threshold","phase","rewrite_shortcut","mysterious"),
    ("boundary_beyond","void","threshold","phase","advance_story","epic"),
    ("borderless_kingdom","fractured","threshold","walk","affect_parent","wonder"),
    ("edge_of_dream","dream","dream","walk","collect_knowledge","serene"),
    ("endless_meadow","identity","passage","walk","awaken_ecology","gentle"),
    ("free_roam_archipelago","identity","vehicle","sail","collect_knowledge","awe"),
    ("courtyard_within","recursive","threshold","walk","unlock_stage","ancient"),
    ("observatory_within","miniature","item","crawl","collect_knowledge","cosmic"),
    ("starship_diorama","miniature","item","scale","upgrade_item","whimsical"),
    ("sword_sanctum","miniature","item","walk","upgrade_item","epic"),
    ("seed_vault","miniature","item","walk","awaken_ecology","lush"),
    ("living_book","recursive","item","echo_step","advance_story","mysterious"),
    ("enchanted_map","mirror_x","item","walk","rewrite_shortcut","wonder"),
    ("pocket_sky","miniature","item","fly","earn_key","whimsical"),
    ("pocket_ocean","submerged","item","swim","collect_knowledge","serene"),
    ("pocket_nebula","astral","item","drift","upgrade_item","cosmic"),
)
@dataclass(frozen=True)
class RealmFamily:
    key:str
    transform:str
    entry:str
    traversal:str
    consequence:str
    tone:str
    novelty_tag:str
    runtime_contract:str="abstract_coordinate_transformation_and_real_nested_travel"

def _canonical(value)->str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)

FAMILIES={}
for row in RAW_FAMILIES:
    key,transform,entry,traversal,consequence,tone=row
    assert key not in FAMILIES and SAFE.fullmatch(key)
    assert transform in TRANSFORMS and entry in ENTRY_MODES
    assert traversal in TRAVERSAL and consequence in CONSEQUENCES
    assert tone in TONE
    FAMILIES[key]=RealmFamily(
        key,transform,entry,traversal,consequence,tone,
        sha256(_canonical(row).encode()).hexdigest()[:16],
    )
assert len(FAMILIES)>=100
assert len(BIOME_CLASSES)>=60

def family(key:str)->RealmFamily:
    if type(key) is not str or key not in FAMILIES:
        raise ValueError("unrecognized original nested world family")
    return FAMILIES[key]

def palette_for(key:str,seed:int)->str:
    family(key)
    if type(seed) is not int or not 0<=seed<2**64:
        raise ValueError("original palette seed outside signed hardware-independent bound")
    index=int(sha256(f"{key}:{seed}:palette".encode()).hexdigest()[:12],16)
    return PALETTE_NAMES[index%len(PALETTE_NAMES)]

def catalog()->dict:
    return {
        "schema":SCHEMA,
        "family_count":len(FAMILIES),
        "implemented_transforms":list(TRANSFORMS),
        "entry_modes":list(ENTRY_MODES),
        "traversal_adapters":list(TRAVERSAL),
        "parent_consequence_kinds":list(CONSEQUENCES),
        "biome_classes":len(BIOME_CLASSES),
        "foliage_types":len(FOLIAGE_TYPES),
        "atmosphere_layers":len(ATMOSPHERE_LAYERS),
        "palettes":len(PALETTE_NAMES),
        "families":{key:asdict(value) for key,value in FAMILIES.items()},
        "rights":"new original names and rules, no third-party worlds/maps/assets",
        "scope":"abstract mechanics and source-level scenic composition, not 3D biome renderers or licensed commercial environments",
    }
