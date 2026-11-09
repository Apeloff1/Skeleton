"""Original 16-path game campaign composition is actual replay, not fabricated titles."""
from __future__ import annotations
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
    PROGRAM_COUNT,make_program,program_from_levels,binary_nucleus,
    initial,perform,replay,MECHANIC_IDS,
)
from skeleton.ai.webcrawler.dragon_original_campaign_forge import (
    SCHEMA,ROUTE_INTENTS,compose_journey,verify_journey,
    sample_experiences,demonstrate_mechanics,
)


def _busy_design():
    return make_program(str(PROGRAM_COUNT-1))


def test_all_16_playstyles_execute_real_bounded_original_player_choices():
    world=_busy_design()
    views=sample_experiences(world,seed=1977,limit=16,steps=30)
    assert views["schema"]==SCHEMA
    assert views["sampled"]==16
    assert 3<=views["distinct_observed_action_sequences"]<=16
    assert views["different_measured_final_stories"]>=3
    assert views["programs_materialized_as_finished_games"]==0
    assert len(views["experiences"])==16
    for index,row in enumerate(views["experiences"]):
        assert row["intent"]==ROUTE_INTENTS[index]
        assert row["actions_executed"]==30
        assert len(row["actions"])==30
        assert row["visited_original_mechanics"]
        assert len(row["world_changes"])>0
        produced=compose_journey(world,route_intent=index,branch_seed=1977,steps=30)
        assert row["final_history_digest"]==produced.final_history_digest
        assert produced==compose_journey(
            world,route_intent=index,branch_seed=1977,steps=30)
        assert verify_journey(world,produced)["verified"]
        assert produced.remains_playable


def test_actual_impractical_route_revisits_environmental_detours_not_just_labels():
    world=_busy_design()
    silly=compose_journey(world,route_intent=2,branch_seed=42,steps=36)
    assert silly.intent=="long_impractical_detour"
    first=[name for name in silly.actions[:3]]
    assert all(x in {
        "practice_scenic_detours",
        "practice_doubleback_caches",
        "practice_rotating_corridors",
    } for x in first)
    assert silly.actions.count("practice_scenic_detours")>=4
    assert len(silly.visited_original_mechanics)<len(silly.actions)
    assert verify_journey(world,silly)["physical_game_journey"]


def test_actual_ending_and_postgame_are_world_actions_not_claimed_story_flags():
    design=[0]*32
    for i in (16,23,24,25,30,31):design[i]=2
    world=program_from_levels(tuple(design))
    route=compose_journey(world,route_intent=12,branch_seed=0,steps=32)
    assert "alternate_conclusions" in route.visited_original_mechanics
    assert route.ending_variants
    assert route.final_era>=0
    assert route.remains_playable
    assert verify_journey(world,route)["experienced_ending_count"]>=1


def test_game_with_no_active_optional_mechanics_is_still_open_ended_but_not_falsely_unique():
    world=make_program("0")
    plan=compose_journey(world,route_intent=15,branch_seed=99,steps=24)
    assert plan.actions==("rest_world",)*24
    assert plan.visited_original_mechanics==()
    assert plan.ending_variants==()
    assert plan.final_era==0
    assert plan.remains_playable
    assert verify_journey(world,plan)["verified"]
    report=sample_experiences(world,limit=16)
    assert report["distinct_observed_action_sequences"]==1


def test_mechanic_generation_witnesses_are_bounded_and_independently_played():
    program=binary_nucleus(16_777_215)
    proof=demonstrate_mechanics(program)
    assert proof["available_original_mechanics"]==24
    assert len(proof["mechanic_execution_witnesses"])==32
    assert all(item["available"] for item in
               proof["mechanic_execution_witnesses"][:24])
    assert all(not item["available"] for item in
               proof["mechanic_execution_witnesses"][24:])
    assert all(item["witness"] for item in
               proof["mechanic_execution_witnesses"][:24])


def test_causal_gameplay_and_route_proof_integrity_catches_edits_to_story_branches():
    world=_busy_design()
    route=compose_journey(world,route_intent=9,branch_seed=2026,steps=32)
    for changed in (
        replace(route,actions=route.actions[:-1]),
        replace(route,final_history_digest="0"*64),
        replace(route,world_changes=()),
        replace(route,actual_resource_changes=(0,)*7),
        replace(route,final_location=(99999,99999)),
        replace(route,ending_variants=("copyrighted_story_ending",)),
    ):
        with pytest.raises(ValueError):
            verify_journey(world,changed)


@pytest.mark.parametrize("values",[
    {"route_intent":-1},{"route_intent":16},{"route_intent":True},
    {"route_intent":1,"branch_seed":-1},
    {"route_intent":1,"branch_seed":2**32},
    {"route_intent":1,"steps":129},
    {"route_intent":1,"steps":0},
])
def test_campaign_gameplay_composer_rejects_unbounded_or_unimplemented_variations(values):
    with pytest.raises(ValueError):
        compose_journey(_busy_design(),**values)


def test_route_sampling_admits_only_actual_bounded_replayed_alternatives():
    with pytest.raises(ValueError):
        sample_experiences(_busy_design(),limit=17)
    with pytest.raises(ValueError):
        sample_experiences(_busy_design(),limit=0)
    with pytest.raises(ValueError):
        sample_experiences(_busy_design(),steps=129)
