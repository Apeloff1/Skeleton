"""Materialize *playable original prototype candidates*, one by exact address.

An original game is more than a random title, maze or seed. Each requested
prototype has (1) a behaviorally separable rule program, (2) a compatible
actual living-world lifecycle, (3) original narrative/terrain direction,
(4) genuinely replayed gameplay examples, (5) machine-verifiable identity,
and (6) explicit unfulfilled art, user-playtest, device and legal signoff.

4,294,967,296 full-width binary rulebook addresses correspond to different *available
mechanic action sets*. That is a mathematical and executable property;
not 4.29b already produced, aesthetically unique or commercially finished
games. No external game assets or copyrighted maps are read or emitted.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
from hashlib import sha256
import json

from .dragon_living_world import (
    WORLD_ADDRESS_COUNT,VARIANTS_PER_ADDRESS,create_world,initial_state,
    describe,terrain,_sha,
)
from .dragon_original_mechanic_forge import (
    OriginalProgram,binary_nucleus,full_binary_nucleus,MECHANICS,
    FULL_BINARY_PROFILE_COUNT,validate_program,capabilities,
    MECHANIC_IDS,MILLION_DISTINCT_ENABLE_PROFILES,
    choices,initial,distinguish,
)
from .dragon_original_campaign_forge import (
    compose_journey,verify_journey,
)
from .dragon_living_world_routes import materialize_route,verify_route

SCHEMA="skeleton.ai.dragon.original_game_prototype.v1"
MAX_PREVIEW=12
TITLES_A=(
    "Copper","Glass","Hollow","Violet","Dawn","Cinder","Quiet","Amber",
    "Verdant","Silver","Winter","Radiant","Moss","Whisper","Sable","Ivory",
    "Riven","Tidal","Clockwork","Skyward","Iron","Starlit","Wandering",
    "Emerald","Luminous","Opaline","Silent","Dusk","Granite","Boreal",
    "Golden","Cerulean",
)
TITLES_B=(
    "Compass","Gardens","Archipelago","Frontier","Pilgrimage","Towers",
    "Chambers","Horizon","Parallax","Sanctuary","Rivers","Labyrinth",
    "Confluence","Forges","Harbors","Valley","Canopy","Observatory",
    "Citadels","Orbits","Lanterns","Nomads","Tides","Chronicle",
    "Driftwood","Undercroft","Moons","Monoliths","Currents","Wilds",
    "Mirrors","Constellation",
)
MOTIVATIONS=(
    "restore ecological balance without enforcing a single final victory",
    "explore a twisting labyrinth whose passages react to each decision",
    "rebuild a community while negotiating the consequences of every alliance",
    "map secret and scenic routes, including deliberately inefficient journeys",
    "discover interlocking worlds and choose when their stories continue",
    "survive the seasons with meaningful resource and settlement tradeoffs",
    "trace forgotten discoveries across shifting societies and world eras",
    "engineer original transport networks across difficult environmental zones",
)
AUDIT_REQUIREMENTS=(
    "original_asset_artwork_and_audio",
    "distinct_character_and_story_editorial_review",
    "human_playtesting_accessibility_and_enjoyment",
    "native_build_per_supported_distribution_target",
    "independent_copyright_trademark_and_license_review",
    "device_performance_and_save_integrity",
    "original_localization_and_age_safety_review",
)

@dataclass(frozen=True)
class OriginalPrototype:
    schema:str
    original_nucleus:int
    title:str
    source_digest:str
    gameplay_program_index:str
    active_mechanics:tuple[str,...]
    available_mechanic_count:int
    independent_domain_count:int
    core_loop_viable:bool
    underbuilt_reasons:tuple[str,...]
    world_style:str
    world_lifecycle:str
    world_source_digest:str
    world_premise:str
    biome:str
    visible_landmark:str
    optional_ending:bool
    persistent_after_ending:bool
    start_action_count:int
    replayed_journeys:tuple[dict,...]
    compared_unique_action_sequences:int
    living_world_actual_route_actions:tuple[str,...]
    living_world_route_digest:str
    living_world_endings:tuple[str,...]
    living_world_remains_playable:bool
    originality_scope:str
    release_blockers:tuple[str,...]
    ready_for_individual_experiments:bool
    native_binary_built:bool
    independently_published:bool
    proof_digest:str


def _world_style(active:set[str])->str:
    """Choose original world systems from actual, enabled rule interactions."""
    if "postgame_repair" in active:
        return "post_story_wasteland"
    if "rotating_corridors" in active and "doubleback_caches" in active:
        return "mutable_labyrinth"
    if "portal_alignment" in active and "orbital_transfer" in active:
        return "multiple_world_platform"
    if "ecology_succession" in active and "creature_migration" in active:
        return "living_ecosystem"
    if "settlement_growth" in active and "artisan_crafting" in active:
        return "colony_simulation"
    if "alternate_conclusions" in active:
        return "branching_campaign"
    if "branching_chronicles" in active:
        return "open_world_story"
    if "survival_foraging" in active and "hardcore_perils" in active:
        return "hardcore_roguelike"
    if "terrain_terraforming" in active and "world_era_cycles" in active:
        return "generational_world"
    if "river_navigation" in active and "open_seas" in active:
        return "oceanic_archipelago"
    if "merchant_convoys" in active and "rail_timelines" in active:
        return "transport_tycoon"
    return "creative_sandbox"


def _canonical(obj)->str:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True)


def materialize(nucleus:int,*,branch_seed:int=0,
                routes:int=4,steps:int=16)->OriginalPrototype:
    if (type(nucleus) is not int or
            not 0<=nucleus<FULL_BINARY_PROFILE_COUNT or
            type(branch_seed) is not int or not 0<=branch_seed<2**32 or
            type(routes) is not int or not 1<=routes<=MAX_PREVIEW or
            type(steps) is not int or not 4<=steps<=64):
        raise ValueError("bounded original game prototype request invalid")
    program=full_binary_nucleus(nucleus)
    active=tuple(MECHANIC_IDS[i] for i,level
                 in enumerate(program.intensities) if level>0)
    world_type=_world_style(set(active))
    world=create_world(
        world_id=nucleus%WORLD_ADDRESS_COUNT,
        variant=(nucleus//WORLD_ADDRESS_COUNT)%VARIANTS_PER_ADDRESS,
        style=world_type,
    )
    location=terrain(world,0,0,0)
    texture=_sha((SCHEMA,nucleus,branch_seed))
    first=int(texture[:8],16)%len(TITLES_A)
    second=int(texture[8:16],16)%len(TITLES_B)
    subject=int(texture[16:24],16)%len(MOTIVATIONS)
    title=f"{TITLES_A[first]} {TITLES_B[second]} · O{nucleus:06X}"
    premise=MOTIVATIONS[subject]
    if "alternate_conclusions" in active:
        premise+="; player-authored choices unlock multiple actual narrative outcomes"
    if "postgame_repair" in active:
        premise+="; reconstruction continues after a formal storyline conclusion"
    journey=[]
    for strategy in range(routes):
        result=compose_journey(program,route_intent=strategy,
                               branch_seed=branch_seed,steps=steps)
        if not verify_journey(program,result)["verified"]:
            raise ValueError("original prototype emitted non-playable campaign example")
        journey.append({
            "intent":result.intent,"actions":result.actions,
            "trace_digest":result.trace_digest,
            "ending_variants":result.ending_variants,
            "location":result.final_location,
            "era":result.final_era,
            "resources_changed":result.actual_resource_changes,
            "actually_replayed":True,
        })
    world_walk=materialize_route(
        world,slot=(nucleus+branch_seed)%10,
        steps=min(48,max(12,steps)),
    )
    if not verify_route(world,world_walk)["verified"]:
        raise ValueError("original prototype world lifecycle failed real play replay")
    domains={MECHANICS[i][1] for i,v in
             enumerate(program.intensities) if v>0}
    unique_play_paths=len({tuple(row["actions"]) for row in journey})
    missing=[]
    if len(active)<4:
        missing.append("fewer_than_four_meaningful_mechanic_systems")
    if len(domains)<3:
        missing.append("fewer_than_three_independent_gameplay_domains")
    if unique_play_paths<2:
        missing.append("no_observed_choice_path_diversity")
    viable=not missing
    candidate={
        "schema":SCHEMA,"original_nucleus":nucleus,"title":title,
        "source_digest":program.source_digest,
        "gameplay_program_index":program.decimal_index,
        "active_mechanics":active,
        "available_mechanic_count":len(active),
        "independent_domain_count":len(domains),
        "core_loop_viable":viable,
        "underbuilt_reasons":tuple(missing),
        "world_style":world.style,"world_lifecycle":world.lifecycle,
        "world_source_digest":world.world_fingerprint,
        "world_premise":premise,
        "biome":location["biome"],
        "visible_landmark":location["landmark"],
        "optional_ending":world.includes_goal,
        "persistent_after_ending":world.allows_continuation,
        "start_action_count":sum(x["available"] for x
                                  in choices(program,initial(program))),
        "replayed_journeys":tuple(journey),
        "compared_unique_action_sequences":unique_play_paths,
        "living_world_actual_route_actions":world_walk.actions,
        "living_world_route_digest":world_walk.trace_digest,
        "living_world_endings":world_walk.original_endings,
        "living_world_remains_playable":world_walk.remains_playable,
        "originality_scope":"distinct original rule-action signature; "
            "narrative/editorial uniqueness not established",
        "release_blockers":AUDIT_REQUIREMENTS+(
            ("original_core_loop_quality_gate",) if not viable else ()
        ),
        "ready_for_individual_experiments":viable,
        "native_binary_built":False,
        "independently_published":False,
    }
    return OriginalPrototype(
        **candidate,proof_digest=_sha(candidate),
    )


def verify_prototype(value:OriginalPrototype, *,
                     branch_seed:int=0)->dict:
    if not isinstance(value,OriginalPrototype) or value.schema!=SCHEMA:
        raise ValueError("unrecognized original executable game candidate")
    if not value.replayed_journeys:
        raise ValueError("original game candidate lacks real gameplay")
    expected=materialize(value.original_nucleus,
                         branch_seed=branch_seed,
                         routes=len(value.replayed_journeys),
                         steps=len(value.replayed_journeys[0]["actions"]))
    if expected!=value:
        raise ValueError("prototype replay or legally reviewed game claim forged")
    return {
        "schema":SCHEMA,"verified":True,
        "active_original_mechanics":len(value.active_mechanics),
        "core_loop_viable":value.core_loop_viable,
        "independent_gameplay_domains":value.independent_domain_count,
        "demonstrated_playable_routes":len(value.replayed_journeys),
        "independent_publication_approved":False,
        "scope":"real gameplay prototype; no art, distribution or legal clearance",
    }


def distinguish_prototypes(left:int,right:int)->dict:
    if left==right:
        raise ValueError("different game prototypes must use distinct original nuclei")
    first=full_binary_nucleus(left)
    second=full_binary_nucleus(right)
    causal=distinguish(first,second)
    if not causal["distinguishable"]:
        raise ValueError("distinct original prototypes unexpectedly share mechanic rules")
    return {
        "schema":SCHEMA,
        "left_nucleus":left,"right_nucleus":right,
        "different_gameplay_rules":True,
        "witness":causal,
        "claim":"distinct executable available actions, not necessarily "
                "distinct original creative literary or visual expression",
    }


def structurally_qualified_capacity()->dict:
    """Exact combinatorial lower filter WITHOUT enumerating billions of worlds.

    Count binary full-width rulebooks with at least four active mechanics
    spanning at least three mechanically independent domains. Does not
    assert player-enjoyment, path variety, visual expression or publication.
    """
    from collections import Counter
    from math import comb
    sizes=Counter(item[1] for item in MECHANICS)
    dp=[[0]*5 for _ in range(4)]
    dp[0][0]=1
    for size in sizes.values():
        following=[[0]*5 for _ in range(4)]
        for old_domains in range(4):
            for old_active in range(5):
                ways=dp[old_domains][old_active]
                if not ways:continue
                following[old_domains][old_active]+=ways
                for count in range(1,size+1):
                    following[min(3,old_domains+1)][min(4,old_active+count)]+=(
                        ways*comb(size,count)
                    )
        dp=following
    acceptable=dp[3][4]
    return {
        "schema":SCHEMA,
        "full_binary_rulebook_addresses":FULL_BINARY_PROFILE_COUNT,
        "min_active_mechanics":4,
        "min_independent_domains":3,
        "exact_structurally_multi_domain_rulebooks":acceptable,
        "thin_rulebooks_filtered":FULL_BINARY_PROFILE_COUNT-acceptable,
        "executable_journey_and_release_review_still_required":True,
        "finished_and_published_games_from_count":0,
    }


def sample_prototypes(*,start:int,count:int,
                      branch_seed:int=0,
                      routes:int=2,steps:int=12)->dict:
    if (type(start) is not int or type(count) is not int or
            not 0<=start<FULL_BINARY_PROFILE_COUNT or
            not 1<=count<=24 or
            start+count>FULL_BINARY_PROFILE_COUNT):
        raise ValueError("original prototype sampling must be small and bounded")
    entries=[materialize(index,branch_seed=branch_seed,
                         routes=routes,steps=steps)
             for index in range(start,start+count)]
    return {
        "schema":SCHEMA,"nuclei_indexed":FULL_BINARY_PROFILE_COUNT,
        "requested_materialized":count,
        "distinct_executable_rulebooks":len({
            x.gameplay_program_index for x in entries}),
        "individually_finished_games":0,
        "prototypes":[asdict(x) for x in entries],
        "scope":"bounded real game candidates with mechanically distinct rulebooks, "
                "not complete independent copyrighted entertainment products",
    }
