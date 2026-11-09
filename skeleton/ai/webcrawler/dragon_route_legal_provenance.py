"""Original game route-world novelty and legal provenance review.

This is an **internal originality-screening mechanism**, not a legal opinion.
It rejects exact-copy graphs, excessive abstract network overlap and missing
asset/license attestations. Abstract routes, ideas and travel modalities
are not copyright claims; real art, dialogue, marks, characters, code and
specific expressive map design require external clearance and review.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
import json
from .dragon_route_world import World,validate_world

SCHEMA="skeleton.ai.dragon.original_route_provenance.v1"
MANDATORY_CLEARANCE=(
    "authored_route_graph_source",
    "original_world_names_and_geography",
    "original_characters_and_dialogue",
    "original_artwork_textures_and_ui",
    "original_music_and_sound",
    "no_unlicensed_trademarks_or_marks",
    "platform_distribution_rights",
    "human_originality_and_similarity_review",
)

@dataclass(frozen=True)
class SourceRights:
    owner_reference:str
    original_creation:bool
    imported_commercial_maps:bool=False
    imported_proprietary_roms:bool=False
    imported_unlicensed_media:bool=False
    individual_clearance:tuple[str,...]=()
    documentation_reference:str=""
    human_reviewer_approved:bool=False

@dataclass(frozen=True)
class OriginalityReview:
    schema:str
    world_sha256:str
    compared_worlds:int
    exact_duplicate_count:int
    highest_structural_similarity_percent:int
    external_asset_risk_flags:tuple[str,...]
    uncompleted_release_checks:tuple[str,...]
    original_game_candidate_eligible:bool
    finished_game_release_approved:bool
    claim:str


def _signature(world:World)->frozenset[tuple[str,...]]:
    # Two forms of evidence: direct named-location topology, and geography-
    # agnostic patterns. Both are needed to avoid mistaking reseeded fares for
    # an entirely new game. A shared mundane taxi connection is not IP theft.
    return frozenset(
        ("route",edge.origin,edge.destination,edge.mode,*sorted(edge.shapes))
        for edge in world.connections
    )

def _abstract_signature(world:World)->frozenset[tuple[str,...]]:
    return frozenset(
        ("abstract",edge.mode,*sorted(edge.shapes),
         str(len(edge.requires)),str(bool(edge.secret_token)),
         str(bool(edge.departures)),str(bool(edge.weather_any)))
        for edge in world.connections
    )

def _percent(lhs:set|frozenset,rhs:set|frozenset)->int:
    all_items=lhs|rhs
    if not all_items:return 100
    return round(len(lhs&rhs)*100/len(all_items))

def assess_route_originality(
    world:World,*,rights:SourceRights,
    reference_worlds:tuple[World,...]=(),
    threshold_percent:int=95,
)->OriginalityReview:
    validate_world(world)
    if not isinstance(rights,SourceRights):
        raise ValueError("source rights must use an exact original provenance record")
    if (type(threshold_percent) is not int or
            not 50<=threshold_percent<=99 or
            not isinstance(reference_worlds,tuple) or
            len(reference_worlds)>64):
        raise ValueError("bounded route-world comparison request invalid")
    if (type(rights.original_creation) is not bool or
            type(rights.imported_commercial_maps) is not bool or
            type(rights.imported_proprietary_roms) is not bool or
            type(rights.imported_unlicensed_media) is not bool or
            type(rights.human_reviewer_approved) is not bool):
        raise ValueError("rights review fields must be explicit booleans")
    if (not isinstance(rights.owner_reference,str) or
            not 4<=len(rights.owner_reference)<=120 or
            not isinstance(rights.documentation_reference,str) or
            len(rights.documentation_reference)>240 or
            not isinstance(rights.individual_clearance,tuple) or
            len(rights.individual_clearance)>len(MANDATORY_CLEARANCE) or
            any(type(name) is not str or name not in MANDATORY_CLEARANCE
                for name in rights.individual_clearance) or
            len(set(rights.individual_clearance))!=len(rights.individual_clearance)):
        raise ValueError("original game rights evidence has invalid identifiers")
    from .dragon_route_world_factory import scenario_digest
    digest=scenario_digest(world)
    exact=0
    similarity=0
    fingerprint=_signature(world)
    # Do not report on a source as truly unique without checking structural
    # shape differences in content; multiple seeds may be graph-equivalent.
    for reference in reference_worlds:
        validate_world(reference)
        if scenario_digest(reference)==digest:exact+=1
        score=_percent(fingerprint,_signature(reference))
        similarity=max(similarity,score)
    risks=[]
    if not rights.original_creation:risks.append("original_authorship_not_attested")
    if rights.imported_commercial_maps:risks.append("commercial_level_expression_import")
    if rights.imported_proprietary_roms:risks.append("proprietary_rom_content_import")
    if rights.imported_unlicensed_media:risks.append("unlicensed_game_asset_import")
    if exact:risks.append("exact_existing_world_duplicate")
    if reference_worlds and similarity>=threshold_percent:
        risks.append("high_structural_overlap_requires_human_review")
    uncompleted=tuple(
        item for item in MANDATORY_CLEARANCE
        if item not in rights.individual_clearance
    )
    eligible=not risks
    cleared=eligible and not uncompleted and rights.human_reviewer_approved
    return OriginalityReview(
        SCHEMA,digest,len(reference_worlds),exact,similarity,
        tuple(risks),uncompleted,eligible,cleared,
        "Only comparisons against explicitly supplied worlds, not global IP "
        "databases. Human lawyer/rightsholder approval is not implied; "
        "the travel-mode taxonomy itself is not protected source expression.",
    )

def assert_original_game_candidate(review:OriginalityReview)->None:
    if not isinstance(review,OriginalityReview) or not review.original_game_candidate_eligible:
        raise ValueError("world game originality candidate rejected")
    # Candidate admission is categorically different from publication signoff.


def assert_full_game_rights_release(review:OriginalityReview)->None:
    if not isinstance(review,OriginalityReview) or not review.finished_game_release_approved:
        raise PermissionError(
            "original playable game still requires documented media, platform "
            "and human review; generic graph originality is not rights clearance"
        )


def review_json(review:OriginalityReview)->dict:
    return asdict(review)
