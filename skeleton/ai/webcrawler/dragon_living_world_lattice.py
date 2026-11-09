"""Reversible lazy design-space indexing; capacity is NOT shipped content.

Actual original world generation can address over three billion valid
(style, lifecycle, world seed, version) configurations without storing all
combinations in RAM/disk. A requested index is materialized as one real
world with runnable game state and replayable routes. This does *not*
claim all indexed configurations are creatively unique or independently
playtested/commercially cleared game titles.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass

from .dragon_living_world import (
    STYLE_NAMES,STYLE_RULES,LIFECYCLES,
    WORLD_ADDRESS_COUNT,VARIANTS_PER_ADDRESS,
    LivingWorld,create_world,validate_world,_sha,
)
from .dragon_living_world_routes import materialize_route,verify_route

SCHEMA="skeleton.ai.dragon.living_design_lattice.v1"

# Six lifecycles are valid for all styles. Hardcore permadeath is only
# activated on genuinely implemented survival/combat styles.
LIFECYCLE_PROFILES=(
    "unending","optional_endings","postgame",
    "multiple_endings","mandatory_completion","restartable_runs",
)
PROFILES=tuple(
    (style,lifecycle) for style in STYLE_NAMES for lifecycle in (
        LIFECYCLE_PROFILES+(
            ("permadeath",) if (
                "survival" in STYLE_RULES[style] or
                "combat" in STYLE_RULES[style]) else ()
        )
    )
)
PROFILE_INDEX={v:i for i,v in enumerate(PROFILES)}
DESIGN_ADDRESS_COUNT=(
    WORLD_ADDRESS_COUNT*VARIANTS_PER_ADDRESS*len(PROFILES)
)
ALTERNATIVE_ACTION_ADDRESS_COUNT=DESIGN_ADDRESS_COUNT*10
assert len(PROFILES)==len(PROFILE_INDEX)
assert DESIGN_ADDRESS_COUNT>1_800_000_000
assert ALTERNATIVE_ACTION_ADDRESS_COUNT>18_000_000_000


@dataclass(frozen=True)
class DesignAddress:
    schema:str
    index:int
    world_id:int
    variation:int
    style:str
    lifecycle:str
    original_world_fingerprint:str
    configuration_digest:str
    actually_materialized:bool
    reviewed_finished_game:bool


def unrank_design(index:int)->DesignAddress:
    if type(index) is not int or not 0<=index<DESIGN_ADDRESS_COUNT:
        raise ValueError("original compositional world design slot out of range")
    world_slot,profile=divmod(index,len(PROFILES))
    world_id,variation=divmod(world_slot,VARIANTS_PER_ADDRESS)
    style,lifecycle=PROFILES[profile]
    world=create_world(world_id=world_id,variant=variation,
                       style=style,lifecycle=lifecycle)
    return DesignAddress(
        schema=SCHEMA,index=index,world_id=world_id,
        variation=variation,style=style,lifecycle=lifecycle,
        original_world_fingerprint=world.world_fingerprint,
        configuration_digest=_sha([
            SCHEMA,index,world.world_fingerprint,
        ]),
        actually_materialized=True,reviewed_finished_game=False,
    )


def rank_design(world:LivingWorld)->int:
    validate_world(world)
    profile=PROFILE_INDEX.get((world.style,world.lifecycle))
    if profile is None:
        raise ValueError("original design lattice does not include unsupported profile")
    return (
        (world.world_id*VARIANTS_PER_ADDRESS+world.variant)*len(PROFILES)
        +profile
    )


def verify_design_address(data:DesignAddress)->dict:
    if not isinstance(data,DesignAddress) or data.schema!=SCHEMA:
        raise ValueError("unrecognized original-world indexed design")
    actual=unrank_design(data.index)
    if actual!=data:
        raise ValueError("original-world index changed identity or rights status")
    world=create_world(world_id=data.world_id,variant=data.variation,
                       style=data.style,lifecycle=data.lifecycle)
    if rank_design(world)!=data.index:
        raise ValueError("compositional design address cannot round trip")
    return {
        "schema":SCHEMA,"verified":True,
        "world":data.world_id,"variation":data.variation,
        "winning_condition_exists":world.includes_goal,
        "playable_without_win":not world.includes_goal,
    }


def route_at_design_index(design_index:int,*,path_slot:int=0)->dict:
    """Actually execute one of ten gameplay choices in any lazy world."""
    addr=unrank_design(design_index)
    world=create_world(world_id=addr.world_id,variant=addr.variation,
                       style=addr.style,lifecycle=addr.lifecycle)
    chosen=materialize_route(world,path_slot)
    receipt=verify_route(world,chosen)
    return {
        "schema":SCHEMA,"design":asdict(addr),
        "route":asdict(chosen),"verification":receipt,
        "claims":"actual requested source game actions; 3b+ index capacity "
                 "is not 3b unique finished titles or already sampled paths",
    }


def lattice_capabilities()->dict:
    return {
        "schema":SCHEMA,
        "style_count":len(STYLE_NAMES),
        "valid_style_lifecycle_profiles":len(PROFILES),
        "world_address_count":WORLD_ADDRESS_COUNT,
        "variants_per_world":VARIANTS_PER_ADDRESS,
        "reversibly_addressable_original_world_configurations":DESIGN_ADDRESS_COUNT,
        "indexed_world_configuration_path_slots":ALTERNATIVE_ACTION_ADDRESS_COUNT,
        "number_materialized_in_this_report":0,
        "number_shipped_and_legally_cleared_in_this_report":0,
        "default_claim":"capacity represents indexed valid generator configurations; "
                         "no global novelty, player experience or legal clearance audit",
    }
