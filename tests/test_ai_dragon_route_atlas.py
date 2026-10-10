"""World-scale multi-region original game progress: real completion proofs."""
from __future__ import annotations
from dataclasses import replace
import json,pytest

from skeleton.ai.webcrawler.dragon_route_atlas import (
    AtlasRequest,build_atlas,verify_atlas,play_atlas,atlas_report,
    MAX_REGIONS,MAX_TOTAL_ROOMS,SCHEMA,
)


@pytest.mark.parametrize("regions,width,height",[
    (2,4,4),(3,4,4),(4,6,6),(6,5,4),(12,8,6),
])
def test_every_original_region_is_completable_and_global_game_reaches_its_goal(
    regions,width,height,
):
    result=build_atlas(AtlasRequest(
        regions=regions,width=width,height=height,
        seed=1977,challenge="challenging",
        scenic_density=75,secret_count=2,
    ))
    proof=result.proof
    assert proof.schema==SCHEMA
    assert proof.regions==regions
    assert proof.rooms==regions*width*height
    assert proof.all_room_proofs_available
    assert proof.regional_climates_verified
    assert proof.reachable_regions==tuple(range(regions))
    assert len(set(proof.world_sha256))==regions
    assert all(item.certificate.location_recovery_count==width*height
               for item in result.worlds)
    assert play_atlas(result,proof.fast_replay_commands)["completed_world"]
    assert play_atlas(result,proof.scenic_replay_commands)["completed_world"]
    assert proof.distinct_regional_goal_paths>=1
    if regions>=3:
        assert proof.distinct_regional_goal_paths>=2
        assert proof.fast_regional_route!=proof.scenic_regional_route
        assert len(proof.fast_replay_commands)<len(proof.scenic_replay_commands)


def test_portal_cannot_skip_unsolved_region_or_invent_unreachable_world():
    atlas=build_atlas(AtlasRequest(regions=4,width=4,height=4,seed=2026))
    with pytest.raises(ValueError):
        play_atlas(atlas,("portal_2",))
    with pytest.raises(ValueError):
        play_atlas(atlas,("portal_3",))
    with pytest.raises(ValueError):
        play_atlas(atlas,("portal_999",))
    with pytest.raises(ValueError):
        play_atlas(atlas,("portal_not_a_number",))
    with pytest.raises(ValueError):
        play_atlas(atlas,("made_up_copyrighted_game_edge",))
    first=atlas.worlds[0].certificate.backbone
    intermediate=play_atlas(atlas,first)
    assert intermediate["regional_play"]["completed"]
    assert {item["destination"] for item in intermediate["portal_choices"]}=={1,2}
    moved=play_atlas(atlas,first+("portal_2",))
    assert moved["region"]==2
    assert moved["visited_regions"]==[0,2]
    assert moved["regional_play"]["world_position"]==atlas.worlds[2].world.start


def test_scenic_and_shortcut_regional_paths_are_distinct_true_playthroughs():
    atlas=build_atlas(AtlasRequest(regions=5,width=6,height=4,seed=99))
    swift=play_atlas(atlas,atlas.proof.fast_replay_commands)
    tour=play_atlas(atlas,atlas.proof.scenic_replay_commands)
    assert swift["completed_world"]
    assert tour["completed_world"]
    assert len(swift["visited_regions"])<len(tour["visited_regions"])
    assert set(tour["visited_regions"])==set(range(5))
    assert len(atlas.proof.fast_replay_commands)<len(atlas.proof.scenic_replay_commands)
    assert all(index in tour["visited_regions"] for index in swift["visited_regions"])


def test_12_regions_represent_actual_576_certified_rooms_not_576_unverified_names():
    atlas=build_atlas(AtlasRequest(regions=12,width=8,height=6,seed=1))
    assert atlas.proof.rooms==MAX_TOTAL_ROOMS
    assert all(region.certificate.location_recovery_count==48
               for region in atlas.worlds)
    assert atlas.proof.distinct_regional_goal_paths>2
    report=atlas_report(atlas)
    assert len(report["regional"])==12
    assert sum(x["rooms"] for x in report["regional"])==576
    assert "single huge" in report["proof"]["guarantee_scope"]


def test_original_regional_world_can_reject_edited_submaze_or_relabelled_exit():
    atlas=build_atlas(AtlasRequest(regions=3,width=4,height=4,seed=741))
    changed=replace(atlas.proof,distinct_regional_goal_paths=999)
    with pytest.raises(ValueError):
        verify_atlas(replace(atlas,proof=changed))
    edited=replace(atlas.worlds[0].certificate,
                   source_seed=atlas.worlds[0].certificate.source_seed+1)
    corrupt_region=replace(atlas.worlds[0],certificate=edited)
    with pytest.raises(ValueError):
        verify_atlas(replace(atlas,worlds=(corrupt_region,)+atlas.worlds[1:]))
    assert verify_atlas(atlas)["status"]=="hierarchical_completion_verified"


@pytest.mark.parametrize("invalid",[
    {"regions":0},{"regions":1},{"regions":MAX_REGIONS+1},
    {"regions":True},{"width":9},{"height":7},{"seed":-1},{"seed":2**32},
    {"scenic_density":101},{"detour_density":-1},{"secret_count":5},
    {"challenge":"frustration_no_recovery"},
    {"climate":"unknown_weather"},
])
def test_universe_generator_denies_unbounded_or_not_implemented_game_worlds(invalid):
    with pytest.raises(ValueError):
        build_atlas(AtlasRequest(**invalid))


def test_original_player_controls_do_not_accept_infinite_regional_hops():
    atlas=build_atlas(AtlasRequest(regions=2,width=4,height=4))
    with pytest.raises(ValueError):
        play_atlas(atlas,("portal_1",)*513)
    with pytest.raises(ValueError):
        play_atlas(atlas,["portal_1"])
