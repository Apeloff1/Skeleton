"""3b+ real reversible generator-address options, not fictional shipped titles."""
from __future__ import annotations
import pytest

from skeleton.ai.webcrawler.dragon_living_world import (
    create_world,initial_state,STYLE_NAMES,
)
from skeleton.ai.webcrawler.dragon_living_world_lattice import (
    SCHEMA,DESIGN_ADDRESS_COUNT,ALTERNATIVE_ACTION_ADDRESS_COUNT,
    PROFILES,rank_design,unrank_design,verify_design_address,
    route_at_design_index,lattice_capabilities,
)


def test_full_lattice_exceeds_large_compositional_capacity_without_any_fake_games():
    data=lattice_capabilities()
    assert data["schema"]==SCHEMA
    assert data["style_count"]>=32
    assert data["valid_style_lifecycle_profiles"]==len(PROFILES)
    assert data["reversibly_addressable_original_world_configurations"]==DESIGN_ADDRESS_COUNT
    assert DESIGN_ADDRESS_COUNT>1_800_000_000
    assert ALTERNATIVE_ACTION_ADDRESS_COUNT>18_000_000_000
    assert data["number_materialized_in_this_report"]==0
    assert data["number_shipped_and_legally_cleared_in_this_report"]==0
    assert "no global novelty" in data["default_claim"]


@pytest.mark.parametrize("index",[
    0,1,5,42,1977,1_000_000,
    DESIGN_ADDRESS_COUNT//2,DESIGN_ADDRESS_COUNT-1,
])
def test_indexed_original_game_designs_reproduce_identical_rules_and_lifecycle(index):
    identity=unrank_design(index)
    assert identity.index==index
    assert identity.schema==SCHEMA
    assert identity.actually_materialized
    assert not identity.reviewed_finished_game
    assert verify_design_address(identity)["verified"]
    world=create_world(world_id=identity.world_id,variant=identity.variation,
                       style=identity.style,lifecycle=identity.lifecycle)
    assert rank_design(world)==index
    assert world.world_fingerprint==identity.original_world_fingerprint
    assert unrank_design(index)==identity


def test_non_winnable_worlds_are_valid_inside_large_lattice():
    indices=[i for i,(style,lifecycle) in enumerate(PROFILES)
             if lifecycle=="unending"]
    assert indices
    for index in indices:
        design=unrank_design(index)
        proof=verify_design_address(design)
        assert proof["playable_without_win"]
        assert not proof["winning_condition_exists"]


def test_original_lattice_can_animate_actual_route_for_any_reachable_address():
    for seed_index in (0,2026,DESIGN_ADDRESS_COUNT//2,
                       DESIGN_ADDRESS_COUNT-1):
        evidence=route_at_design_index(seed_index,path_slot=4)
        assert evidence["verification"]["verified"]
        assert evidence["route"]["slot"]==4
        assert evidence["route"]["trace_digest"]
        assert len(evidence["route"]["actions"])>=4
        assert evidence["route"]["world_id"]==evidence["design"]["world_id"]
        assert not evidence["design"]["reviewed_finished_game"]


def test_real_story_ending_and_current_world_history_are_not_fake_config_counts():
    for index,(style,lifecycle) in enumerate(PROFILES):
        if style=="open_world_story" and lifecycle=="postgame":
            evidence=route_at_design_index(index,path_slot=7)
            assert "civic_union" in evidence["route"]["original_endings"]
            assert evidence["route"]["remains_playable"]
            break
    else:
        pytest.fail("original postgame story must be addressable")


@pytest.mark.parametrize("bad",[
    -1,DESIGN_ADDRESS_COUNT,True,None,1.5,
])
def test_outside_compositional_game_world_lattice_is_rejected(bad):
    with pytest.raises(ValueError):
        unrank_design(bad)


@pytest.mark.parametrize("slot",[-1,10,True])
def test_original_lattice_refuses_nonexistent_route_alternative_slot(slot):
    with pytest.raises(ValueError):
        route_at_design_index(0,path_slot=slot)
