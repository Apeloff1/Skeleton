"""Authenticated changing-maze solver with optional waypoints, not a fake win."""
from __future__ import annotations
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_living_world_checkpoint import SECRET_SETTING


def owner():
    return route._native_source_editor({
        "email":"temporal-maze-creator@example.test",
        "tenant_id":"maze-garden","role":"editor",
    })


def request(**kwargs):
    values={
        "world_id":1977,"variation":4,
        "style":"mutable_labyrinth","lifecycle":"unending",
        "delta_x":2,"delta_y":1,"horizon":26,"search_budget":2400,
    }
    values.update(kwargs)
    return route.NativeTemporalMazeRequest(**values)


def test_actual_moving_world_has_two_waypoint_planners_without_mandatory_ending():
    data=route.native_living_world_temporal_maze(request(),owner=owner())
    assert data["ok"]
    assert data["schema"]=="skeleton.ai.dragon.temporal_maze_analysis.v1"
    assert not data["current"]["fixed_winning_condition_exists"]
    assert data["current"]["playable"]
    assert data["target"]=={"realm":0,"x":2,"y":1}
    assert data["solvers"]["both_confirmed"]
    assert data["solvers"]["same_optimal_turn_count"]
    assert len(data["shifting_topology"]["phases"])==8
    assert data["shifting_topology"]["distinct_topologies"]>=2


def test_changing_maze_uses_replayed_player_history_before_planning_new_route():
    data=route.native_living_world_temporal_maze(request(
        moves=["north","wait","forage","rest"]),owner=owner())
    assert data["ok"]
    assert data["current"]["player"]["y"]==-1
    assert data["current"]["player"]["turn"]==4
    assert data["target"]=={"realm":0,"x":2,"y":0}
    assert data["solvers"]["bfs"]["start_digest"]==(
        data["current"]["player"]["history_digest"])
    assert data["solvers"]["both_confirmed"]


def test_original_player_can_analyze_signed_current_state_after_multiple_turns(monkeypatch):
    monkeypatch.setenv(SECRET_SETTING,
        "original-game-temporal-route-solver-signing-key-safeguard-2026")
    body=route.NativeLivingCheckpointRequest(
        world_id=1977,variation=4,style="mutable_labyrinth",
        lifecycle="unending",moves=["north","wait","rest"],
    )
    played=route.native_living_world_checkpoint_advance(body,owner=owner())
    assert played["ok"]
    report=route.native_living_world_temporal_maze(request(
        checkpoint_token=played["new_checkpoint"]),owner=owner())
    assert report["ok"]
    assert report["current"]["player"]["turn"]==3
    assert report["solvers"]["astar"]["start_digest"]==(
        played["current_history_digest"])


@pytest.mark.parametrize("endpoint",[
    "/api/dragon-academy/native/production/worlds/maze/analyze",
])
def test_temporal_maze_analysis_is_not_accessible_to_anonymous_viewers(endpoint):
    selected=next(x for x in route.router.routes if x.path==endpoint)
    assert any(x.call is route._native_source_editor
               for x in selected.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid","role":"viewer",
            "tenant_id":"maze-garden",
        })
    assert denied.value.status_code==403


def test_nonshifting_original_game_is_not_laundered_as_a_rotating_maze():
    with pytest.raises(HTTPException) as denied:
        route.native_living_world_temporal_maze(request(
            style="creative_sandbox"),owner=owner())
    assert denied.value.status_code==422


@pytest.mark.parametrize("invalid",[
    {"delta_x":5},{"delta_x":True},{"delta_y":-5},
    {"delta_x":0,"delta_y":0,"search_budget":99},
    {"search_budget":9999},{"search_budget":True},
    {"horizon":49},{"horizon":0},{"radius":4},
    {"checkpoint_token":77},
    {"checkpoint_token":"x"*12001},
])
def test_exact_changing_maze_analysis_limits_unbounded_or_unsafe_requests(invalid):
    with pytest.raises(ValidationError):
        request(**invalid)
