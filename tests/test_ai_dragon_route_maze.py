"""Constructive original-game mazes: deterministic completion, real doublebacks."""
from __future__ import annotations

from dataclasses import asdict,replace
import json
import pytest

from skeleton.ai.webcrawler.dragon_route_maze import (
    SCHEMA,WEATHERS,MazeRequest,build_maze,verify_maze,recover_maze,_main_spine,
)
from skeleton.ai.webcrawler.dragon_route_world import (
    replay,experience,validate_world,
)
from skeleton.ai.webcrawler.dragon_route_world_assurance import audit_world


@pytest.mark.parametrize("width,height",[
    (4,4),(4,6),(5,4),(6,6),(7,5),(8,6),
])
def test_every_original_maze_room_has_constructively_verified_goal_path(
    width,height,
):
    built=build_maze(MazeRequest(width=width,height=height,seed=1907,
                                 secret_count=2,scenic_density=60,
                                 detour_density=70))
    world,hero,proof=built.world,built.traveller,built.certificate
    validate_world(world)
    assert proof.schema==SCHEMA
    assert len(world.places)==width*height
    assert proof.location_recovery_count==width*height
    assert set(proof.location_recovery_verified)=={
        place.id for place in world.places}
    assert set(proof.all_climates_backbone_verified)==set(WEATHERS)
    assert len(proof.backbone_locations)==len(_main_spine(width,height))
    assert proof.backbone_moves==len(proof.backbone_locations)-1
    assert len(proof.real_dead_ends)>=width
    assert proof.doubleback_witnesses
    assert proof.return_edges
    assert len(world.connections)<=192
    result=verify_maze(built)
    assert result["status"]=="constructively_complete"
    assert result["rooms"]==width*height
    baseline=replay(world,proof.backbone,hero,
                    objective="constructive_backbone")
    assert baseline.digest==proof.main_journey_digest
    assert baseline.success and baseline.places[-1]==world.goal
    for climate in WEATHERS:
        rainy=replace(world,environment=(climate,))
        assert replay(rainy,proof.backbone,hero).success


@pytest.mark.parametrize("seed",[
    0,1,2,17,42,2026,1977,4096,2**32-1,
])
def test_maze_routes_vary_with_seed_but_every_single_world_replays(
    seed,
):
    item=build_maze(MazeRequest(seed=seed,width=5,height=4,
                                scenic_density=90,detour_density=90))
    assert verify_maze(item)["status"]=="constructively_complete"
    assert item.certificate.doubleback_witnesses
    assert item.certificate.secret_witnesses
    assert item.certificate.scenic_witnesses


def test_real_dead_end_contains_reward_and_reverse_move_then_unlockable_shortcut():
    item=build_maze(MazeRequest(seed=1977,width=6,height=6,
                                scenic_density=90))
    world,hero,proof=item.world,item.traveller,item.certificate
    initial=experience(world,hero)
    assert not any("secret" in option["shape"] for option in initial["options"])
    assert len(proof.secret_witnesses)>=1
    for itinerary in proof.secret_witnesses:
        victory=replay(world,itinerary,hero)
        assert victory.success
        assert victory.secret_edges>=1
        assert victory.unlockable_edges>=1
        assert "doubleback" in victory.shapes
        assert "hidden" in victory.shapes
        assert "shortcut" in victory.shapes
        assert victory.loops>0
        assert itinerary!=proof.backbone


def test_scenic_routes_are_real_longer_spur_loops_not_relabelled_fastest_route():
    item=build_maze(MazeRequest(seed=321,scenic_density=100,detour_density=100))
    base=replay(item.world,item.certificate.backbone,item.traveller)
    assert item.certificate.scenic_witnesses
    for route in item.certificate.scenic_witnesses:
        outcome=replay(item.world,route,item.traveller)
        assert outcome.success
        assert outcome.length>base.length
        assert outcome.elapsed_minutes>base.elapsed_minutes
        assert outcome.loops>=1
        assert "scenic" in outcome.shapes
        assert "doubleback" in outcome.shapes


def test_intentionally_impractical_long_routes_are_real_repeatable_gameplay():
    item=build_maze(MazeRequest(seed=531,challenge="spicy",width=6,height=6))
    safe=replay(item.world,item.certificate.backbone,item.traveller)
    assert item.certificate.impractical_witnesses
    for path in item.certificate.impractical_witnesses:
        played=replay(item.world,path,item.traveller)
        assert played.success
        assert played.length>safe.length+6
        assert played.elapsed_minutes>safe.elapsed_minutes
        assert played.loops>=4
        assert "impractical" in played.shapes
        assert "doubleback" in played.shapes


def test_maze_ordinary_backtracking_is_always_costless_and_recoverable():
    item=build_maze(MazeRequest(seed=7,width=8,height=6))
    routes={edge.id:edge for edge in item.world.connections}
    for return_id in item.certificate.return_edges:
        edge=routes[return_id]
        assert edge.price==0
        assert edge.fatigue==0
        assert edge.fuel==0 and edge.oxygen==0 and edge.mana==0
        assert not edge.requires
        assert not edge.weather_any and not edge.weather_none
        assert "safe_return" not in edge.shapes or "recovery" in edge.shapes
    assert "arbitrary resource/time/action exhaustion" in (
        item.certificate.guarantee_scope)


def test_maze_attestation_detects_arbitrary_edge_changes_even_if_author_updates_digest():
    item=build_maze(MazeRequest(seed=7,width=5,height=4))
    world=replace(item.world,connections=(
        replace(item.world.connections[0],minutes=999),)+
        item.world.connections[1:])
    with pytest.raises(ValueError):
        verify_maze(replace(item,world=world))
    corrupted=replace(item.certificate,
        location_recovery_verified=item.certificate.location_recovery_verified[:-1])
    with pytest.raises(ValueError):
        verify_maze(replace(item,certificate=corrupted))
    with pytest.raises(ValueError):
        verify_maze(replace(item,request=replace(item.request,seed=123)))


def test_maze_rich_variants_are_structural_routes_not_unverified_game_titles():
    item=build_maze(MazeRequest(seed=100,width=8,height=6,
        scenic_density=95,detour_density=100,secret_count=4,
        challenge="spicy",weather="storm"))
    report=verify_maze(item)
    shapes=set(item.certificate.optional_shapes)
    assert {"critical","spine","scenic","doubleback","detour",
            "secret","hidden","unlockable","shortcut","free_roam"}<=shapes
    assert item.certificate.location_recovery_count==48
    assert report["status"]=="constructively_complete"
    assert "player enjoyment" in item.certificate.guarantee_scope


@pytest.mark.parametrize("kwargs",[
    {"width":3},{"width":9},{"height":3},{"height":7},
    {"seed":-1},{"seed":2**32},{"seed":True},{"secret_count":5},
    {"scenic_density":101},{"detour_density":-1},
    {"weather":"unsupported"},{"challenge":"unfair_trap"},
])
def test_all_original_game_maze_inputs_are_strictly_bounded(kwargs):
    with pytest.raises(ValueError):
        build_maze(MazeRequest(**kwargs))



def test_actual_current_maze_world_state_has_proven_safe_escape_after_doubleback():
    built=build_maze(MazeRequest(seed=1977,width=6,height=6))
    witness=built.certificate.doubleback_witnesses[0]
    entering=next(index for index,action in enumerate(witness)
                  if action.startswith("branch_"))
    partial=witness[:entering+1]
    proof=recover_maze(built,partial)
    assert proof["reachable_now"]
    assert not proof["reset_required"]
    assert proof["next_move"]
    assert proof["remaining_actions"]==len(proof["recovery_suffix"])
    completed=replay(
        built.world,partial+tuple(proof["recovery_suffix"]),
        built.traveller,
    )
    assert completed.success
    assert "current position" in proof["proof"]


def test_exhausted_80_move_original_world_requires_true_reset_not_fake_shortcut():
    built=build_maze(MazeRequest(seed=1977,width=4,height=4))
    spine=built.certificate.backbone[0]
    returning=next(x.id for x in built.world.connections
                   if x.origin==built.world.connections[0].destination
                   and x.destination==built.world.start
                   and "recovery" in x.shapes)
    history=(spine,returning)*40
    report=recover_maze(built,history)
    assert not report["reachable_now"]
    assert report["reset_required"]
    assert report["next_move"] is None
    assert report["recovery_suffix"]==[]
    assert "restart" in report["proof"]


def test_original_safe_maze_escape_honors_every_climate_and_rejects_illegal_input():
    for weather in WEATHERS:
        built=build_maze(MazeRequest(seed=313,width=5,height=4,weather=weather))
        for target in built.certificate.doubleback_witnesses[:2]:
            entering=next(i for i,name in enumerate(target)
                          if name.startswith("branch_"))
            history=target[:entering+1]
            result=recover_maze(built,history)
            assert result["reachable_now"]
            assert replay(built.world,history+tuple(result["recovery_suffix"]),
                          built.traveller).success
        with pytest.raises(ValueError):
            recover_maze(built,("fake_level_jump",))
