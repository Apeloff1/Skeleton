"""Materialized originals are playable prototypes, not random renamed seeds."""
from __future__ import annotations

from dataclasses import replace
import json
import pytest

from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
    MECHANIC_IDS,MILLION_DISTINCT_ENABLE_PROFILES,
    FULL_BINARY_PROFILE_COUNT,full_binary_nucleus,distinguish,
)
from skeleton.ai.webcrawler.dragon_original_prototype_factory import (
    SCHEMA,MAX_PREVIEW,materialize,verify_prototype,
    sample_prototypes,distinguish_prototypes,
)


def nucleus(*active):
    return sum(1<<(31-i) for i in active)


@pytest.mark.parametrize("candidate",[
    0,1,2,3,42,2026,1_000_000,2**23,16_777_215,
])
def test_every_requested_original_game_has_concrete_separable_actions_world_and_journeys(candidate):
    original=materialize(candidate,branch_seed=1977,routes=3,steps=16)
    assert original.schema==SCHEMA
    assert original.original_nucleus==candidate
    assert original.source_digest==full_binary_nucleus(candidate).source_digest
    assert original.available_mechanic_count==candidate.bit_count()
    assert len(original.active_mechanics)==candidate.bit_count()
    assert original.active_mechanics==tuple(
        MECHANIC_IDS[i] for i in range(32) if candidate&(1<<(31-i))
    )
    assert original.start_action_count>=1
    assert len(original.replayed_journeys)==3
    assert all(item["actually_replayed"] for item in original.replayed_journeys)
    assert all(len(item["actions"])==16 for item in original.replayed_journeys)
    assert original.living_world_actual_route_actions
    assert original.living_world_route_digest
    assert original.originality_scope.startswith("distinct original")
    assert original.ready_for_individual_experiments
    assert not original.native_binary_built
    assert not original.independently_published
    assert original.release_blockers
    assert verify_prototype(original,branch_seed=1977)["verified"]
    assert materialize(candidate,branch_seed=1977,routes=3,steps=16)==original


@pytest.mark.parametrize("indices,expected_style",[
    ((6,7),"mutable_labyrinth"),
    ((10,13),"multiple_world_platform"),
    ((14,15),"living_ecosystem"),
    ((16,18),"colony_simulation"),
    ((23,24),"branching_campaign"),
    ((24,),"branching_campaign"),
    ((25,),"post_story_wasteland"),
    ((26,27),"hardcore_roguelike"),
    ((1,12),"oceanic_archipelago"),
    ((20,11),"transport_tycoon"),
    ((30,31),"generational_world"),
])
def test_original_mechanics_actually_select_corresponding_world_systems(indices,expected_style):
    value=nucleus(*indices)
    world=materialize(value,routes=2,steps=12)
    assert world.world_style==expected_style
    assert world.available_mechanic_count==len(indices)
    assert world.living_world_route_digest
    if expected_style=="post_story_wasteland":
        assert world.persistent_after_ending
    if expected_style in ("creative_sandbox","living_ecosystem",
                          "mutable_labyrinth"):
        assert not world.optional_ending


def test_first_million_unique_indexed_game_prototypes_have_distinct_executable_rulebook_witness():
    assert MILLION_DISTINCT_ENABLE_PROFILES==16_777_216
    for left,right in (
        (0,1),(1,2),(1000,1001),(999_999,1_000_000),
        (MILLION_DISTINCT_ENABLE_PROFILES-2,
         MILLION_DISTINCT_ENABLE_PROFILES-1),
    ):
        evidence=distinguish_prototypes(left,right)
        assert evidence["different_gameplay_rules"]
        assert evidence["witness"]["distinguishable"]
        assert evidence["witness"]["left"]!=evidence["witness"]["right"]


def test_real_short_sample_contains_mechanically_distinct_playable_originals_not_shipped_titles():
    corpus=sample_prototypes(start=4096,count=12,branch_seed=7,
                             routes=2,steps=12)
    assert corpus["schema"]==SCHEMA
    assert corpus["nuclei_indexed"]==FULL_BINARY_PROFILE_COUNT
    assert corpus["requested_materialized"]==12
    assert corpus["distinct_executable_rulebooks"]==12
    assert corpus["individually_finished_games"]==0
    assert len(corpus["prototypes"])==12
    assert all(len(item["proof_digest"])==64 for item in corpus["prototypes"])
    assert all(not item["native_binary_built"] for item in corpus["prototypes"])
    assert all(item["living_world_actual_route_actions"]
               for item in corpus["prototypes"])
    assert len(json.dumps(corpus))<150_000


def test_forged_native_release_or_story_ending_is_rejected_by_full_dual_gameplay_rebuild():
    original=materialize(nucleus(23,24,25),routes=2,steps=12)
    for fake in (
        replace(original,native_binary_built=True),
        replace(original,independently_published=True),
        replace(original,release_blockers=()),
        replace(original,gameplay_program_index="0"),
        replace(original,world_style="creative_sandbox"),
        replace(original,living_world_actual_route_actions=()),
        replace(original,living_world_route_digest="0"*64),
        replace(original,proof_digest="x"*64),
        replace(original,replayed_journeys=()),
    ):
        with pytest.raises(ValueError):
            verify_prototype(fake)


@pytest.mark.parametrize("values",[
    {"nucleus":-1},{"nucleus":FULL_BINARY_PROFILE_COUNT},
    {"nucleus":True},{"nucleus":2,"routes":13},
    {"nucleus":2,"routes":0},{"nucleus":2,"steps":3},
    {"nucleus":2,"steps":65},{"nucleus":2,"branch_seed":-1},
    {"nucleus":2,"branch_seed":2**32},
])
def test_original_game_candidate_materialization_has_strict_bounded_budgets(values):
    with pytest.raises(ValueError):
        materialize(**values)


def test_original_candidate_sampling_cannot_claim_to_have_built_a_million_games():
    with pytest.raises(ValueError):
        sample_prototypes(start=0,count=MAX_PREVIEW+13)
    with pytest.raises(ValueError):
        sample_prototypes(start=FULL_BINARY_PROFILE_COUNT-1,count=2)
    with pytest.raises(ValueError):
        sample_prototypes(start=True,count=3)



def test_full_four_billion_nuclei_cover_all_32_real_game_systems():
    assert FULL_BINARY_PROFILE_COUNT==4_294_967_296
    maximum=materialize(FULL_BINARY_PROFILE_COUNT-1,routes=2,steps=12)
    assert maximum.available_mechanic_count==32
    assert maximum.world_style=="post_story_wasteland"
    assert "postgame_repair" in maximum.active_mechanics
    assert "world_era_cycles" in maximum.active_mechanics
    assert maximum.persistent_after_ending
    assert len(maximum.replayed_journeys)==2
    assert verify_prototype(maximum)["verified"]
    before=full_binary_nucleus(FULL_BINARY_PROFILE_COUNT-2)
    after=full_binary_nucleus(FULL_BINARY_PROFILE_COUNT-1)
    assert distinguish(before,after)["distinguishable"]
