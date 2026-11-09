"""Exact arbitrary-precision genome lattice, every-axis consequences, replayed paths."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_living_world import create_world
from skeleton.ai.webcrawler.dragon_world_genome import (
    SCHEMA,AXIS_NAMES,AXIS_DOMAINS,GENOME_VARIATIONS,GENOMIC_WORLD_COUNT,
    Genome,genome_code,genome_from_code,integer_address,
    unrank_genome_address,rank_genome_address,edit_genome,genome_world,
    lattice_summary,
)
from skeleton.ai.webcrawler.dragon_living_world_lattice import (
    DESIGN_ADDRESS_COUNT,unrank_design,
)
from skeleton.ai.webcrawler.dragon_genomic_world import (
    AXIS_ACTIONS,SCHEMA as GAME_SCHEMA,initial_genomic_state,
    cell,legal_actions,play,replay_genomic,report,
)
from skeleton.ai.webcrawler.dragon_genomic_paths import (
    PROGRAM_COUNT,GLOBAL_CHOICE_PATH_COUNT,CHOICE_VERBS,
    word_code,code_word,rank_path,unrank_path,materialize_path,
    verify_path,sample_paths,pathspace_summary,
)


def test_true_cardinality_is_far_above_quintillions_and_no_materialization_claim():
    assert len(AXIS_NAMES)==len(AXIS_DOMAINS)==len(AXIS_ACTIONS)==24
    assert GENOME_VARIATIONS==16**24==2**96
    assert GENOMIC_WORLD_COUNT==DESIGN_ADDRESS_COUNT*2**96
    assert GENOMIC_WORLD_COUNT>10**36
    assert PROGRAM_COUNT==16**16==2**64
    assert GLOBAL_CHOICE_PATH_COUNT==GENOMIC_WORLD_COUNT*2**64
    assert GLOBAL_CHOICE_PATH_COUNT>10**55
    overview=lattice_summary()
    assert overview["controlled_simulation_axes"]==24
    assert overview["reversibly_addressable_world_configurations"]==str(
        GENOMIC_WORLD_COUNT)
    assert overview["worlds_enumerated_for_this_report"]==0
    assert overview["completed_or_legally_cleared_games"]==0
    assert pathspace_summary()["globally_addressable_choice_paths"]==str(
        GLOBAL_CHOICE_PATH_COUNT)


@pytest.mark.parametrize("value",[
    0,1,15,16,255,256,2**32,2**64,2**88,2**96-1,
])
def test_full_96_bit_genome_can_be_encoded_and_decoded_without_float_loss(value):
    item=genome_from_code(value)
    assert len(item.levels)==24
    assert genome_code(item)==value
    assert genome_from_code(genome_code(item))==item


@pytest.mark.parametrize("index",[
    "0","1","15","16",
    str(2**96-1),str(2**96),str(2**120),
    str(GENOMIC_WORLD_COUNT//2),str(GENOMIC_WORLD_COUNT-1),
])
def test_big_int_world_addresses_are_exact_reversible_and_playable(index):
    address=unrank_genome_address(index)
    assert address.schema==SCHEMA
    assert address.decimal_index==index
    assert address.actual_game_configuration
    assert not address.completed_unique_game
    world,genes=genome_world(address)
    assert rank_genome_address(world,genes)==index
    assert address.world_id==world.world_id
    assert address.style==world.style
    assert address.lifecycle==world.lifecycle
    state=initial_genomic_state(address)
    assert state.choices==0
    assert report(address,state,radius=1)["player"]["base"]["turn"]==0


@pytest.mark.parametrize("invalid",[
    "", "00", "01", "+4", "-1", "1e30", "1.0", " 10", "10 ",
    str(GENOMIC_WORLD_COUNT), "9"*100, 0, True,
])
def test_large_address_decoder_rejects_unsafe_float_or_noncanonical_index(invalid):
    with pytest.raises(ValueError):
        unrank_genome_address(invalid)


def test_all_24_axes_independently_change_a_real_executed_gameplay_result():
    # Not mere hash identities: each trait has its own playable verb and
    # changing its 4-bit value changes that action's actual saved state.
    base=unrank_genome_address("0")
    assert base.levels==(0,)*24
    for i,axis in enumerate(AXIS_NAMES):
        bigger=edit_genome("0",{axis:15})
        assert bigger.levels[i]==15
        assert sum(bigger.levels)==15
        assert bigger.genome_digest!=base.genome_digest
        before=initial_genomic_state(base)
        after=initial_genomic_state(bigger)
        verb=AXIS_ACTIONS[i]
        if verb=="found_outpost":
            before=play(base,before,"prospect_ore")
            after=play(bigger,after,"prospect_ore")
            # Higher building complexity may require extra extraction.
            while not next(x for x in legal_actions(bigger,after)
                           if x["name"]==verb)["available"]:
                after=play(bigger,after,"prospect_ore")
        a=play(base,before,verb)
        b=play(bigger,after,verb)
        assert a.signals[i]==1
        assert b.signals[i]==16
        assert a.history_digest!=b.history_digest
        assert a.choices>=1 and b.choices>=1


def test_genome_controls_change_real_original_terrain_and_traversal_rules():
    base=unrank_genome_address("0")
    mountain=edit_genome("0",{
        "terrain_elevation":15,"traversal_drag":15,
        "weather_violence":15,"watershed":15,
        "sky_islands":15,
    })
    quiet=cell(base,initial_genomic_state(base),0,0,0)
    extreme=cell(mountain,initial_genomic_state(mountain),0,0,0)
    assert quiet["genomic_environment"]["travel_friction"]==1
    assert extreme["genomic_environment"]["travel_friction"]==16
    assert quiet["genomic_environment"]["season_length"]==1
    assert extreme["genomic_environment"]["water_depth"]>=30
    assert extreme["genomic_environment"]["sky_density"]>=15
    base_move=next(x for x in legal_actions(base,initial_genomic_state(base))
                   if x["name"]=="north")
    extreme_move=next(x for x in legal_actions(
        mountain,initial_genomic_state(mountain)) if x["name"]=="north")
    assert extreme_move["genomic_cost"]>base_move["genomic_cost"]
    assert quiet["genome_cell_sha256"]!=extreme["genome_cell_sha256"]


def test_24_game_controls_have_real_replayable_resource_and_knowledge_results():
    addr=unrank_genome_address(str(2**96-1))
    first=initial_genomic_state(addr)
    acts=(
        "survey_elevation","map_biomes","study_river","explore_caves",
        "scan_skies","forecast_storm","study_seasons","chart_stars",
        "tend_flora","track_fauna","forage_food","prospect_ore",
        "plan_building","mediate_dispute","scout_pass","trace_shifting_wall",
    )
    current=replay_genomic(addr,acts)
    assert current.choices==16
    assert current.base.turn==16
    assert current.material>first.material
    assert current.knowledge>first.knowledge
    assert current.portal_charge>first.portal_charge
    assert current.history_digest!=first.history_digest
    assert current==replay_genomic(addr,acts)
    assert all(current.signals[i]>=1 for i in (
        0,1,2,3,4,5,6,7,8,9,10,11,12,15,17,18
    ))


@pytest.mark.parametrize("world_index",[
    "0","1",str(2**96-1),str(2**96),
    str(GENOMIC_WORLD_COUNT//2),
    str(GENOMIC_WORLD_COUNT-1),
])
def test_each_big_world_supports_sixteen_real_original_player_choices(world_index):
    # Routes are actual game actions, not just untrusted labels.
    index=rank_path(world_index,tuple(range(16)))
    world,word=unrank_path(index)
    assert world.decimal_index==world_index
    assert word==tuple(range(16))
    receipt=materialize_path(index)
    assert receipt.actually_played
    assert len(receipt.actions)==16
    assert len(set(receipt.actions))==16
    assert receipt.final_turn==16
    assert receipt.local_program_code==str(word_code(word))
    assert verify_path(receipt)["verified"]


@pytest.mark.parametrize("code",[
    0,1,15,16,16**8,16**16-1,
])
def test_route_action_programs_reverse_exactly_even_at_64_bit_boundary(code):
    assert word_code(code_word(code))==code
    assert len(code_word(code))==16
    assert all(0<=x<=15 for x in code_word(code))


def test_distinct_16_digit_paths_are_really_distinct_observed_action_histories():
    addr="0"
    a=materialize_path(rank_path(addr,(0,)*16))
    b=materialize_path(rank_path(addr,(15,)*16))
    c=materialize_path(rank_path(addr,(0,)*15+(1,)))
    assert a.actions!=b.actions!=c.actions
    assert a.execution_digest!=b.execution_digest!=c.execution_digest
    assert a.final_history_digest!=b.final_history_digest
    assert b.sampled_signals!=a.sampled_signals
    assert all(not row.finished_game_release_approved for row in (a,b,c))


def test_four_sampled_routes_get_real_playback_and_truthful_uniqueness_count():
    sampled=sample_paths("0",limit=4)
    assert sampled["sampled_count"]==4
    assert sampled["distinct_actual_action_histories"]==4
    assert len(sampled["routes"])==4
    assert "only these sampled paths" in sampled["claim"]


def test_forged_game_result_cannot_claim_an_unplayed_ending_or_route():
    route=materialize_path("0")
    for fake in (
        replace(route,final_turn=999),
        replace(route,execution_digest="0"*64),
        replace(route,final_history_digest="a"*64),
        replace(route,finished_game_release_approved=True),
        replace(route,actions=("copied_game_move",)*16),
    ):
        with pytest.raises(ValueError):
            verify_path(fake)


@pytest.mark.parametrize("fake",[
    "00","1.0","2e50","-1",str(GLOBAL_CHOICE_PATH_COUNT),"9"*120,
])
def test_global_quintillion_plus_route_addresses_are_exact_strings(fake):
    with pytest.raises(ValueError):
        unrank_path(fake)
