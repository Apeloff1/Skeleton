"""Actual time-dependent maze path planning, no global victory requirement."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_living_world import (
    create_world,initial_state,replay,take_action,options,
)
from skeleton.ai.webcrawler.dragon_living_maze_solvers import (
    SCHEMA,solve,compare_solvers,changing_doors,verify_proof,
)


@pytest.mark.parametrize("style",[
    "mutable_labyrinth","rotating_tower","shifting_dungeon",
    "time_loop_maze","living_castle",
])
@pytest.mark.parametrize("goal",[(0,2,0),(0,-2,1),(0,1,2)])
def test_two_independent_solvers_find_actual_waypoints_in_changing_maze(style,goal):
    world=create_world(world_id=2026,variant=3,style=style)
    evidence=compare_solvers(world,goal,budget=3000,horizon=24)
    assert evidence["schema"]==SCHEMA
    assert evidence["independent_solvers"]==[
        "time_expanded_bfs","admissible_temporal_astar",
    ]
    assert evidence["both_confirmed"]
    assert evidence["same_optimal_turn_count"]
    assert evidence["world_goal_required"]==(world.includes_goal)
    for solver in ("bfs","astar"):
        row=evidence[solver]
        played=replay(world,tuple(row["steps"]))
        assert played.realm==goal[0]
        assert (played.x,played.y)==goal[1:]
        assert played.history_digest==row["replay_digest"]
        assert row["actual_turns"]==len(row["steps"])
        assert row["movement_turns"]+row["waiting_turns"]==len(row["steps"])


def test_temporal_maze_door_topology_is_physically_different_between_phases():
    world=create_world(world_id=1977,variant=6,style="mutable_labyrinth")
    projection=changing_doors(world,realm=0,x=0,y=0,radius=2)
    assert projection["schema"]==SCHEMA
    assert len(projection["phases"])==8
    assert projection["distinct_topologies"]>=2
    assert projection["total_projected_directed_nodes"]==8*25
    assert len({frame["fingerprint"] for frame in projection["phases"]})>=2
    for phase in projection["phases"]:
        assert len(phase["links"])==25
        assert all(entry["open"] for entry in phase["links"])
        assert all(name in {"north","east","south","west"}
                   for entry in phase["links"] for name in entry["open"])


def test_temporal_planner_can_plan_real_move_after_waiting_for_wall_to_rotate():
    world=create_world(world_id=1977,variant=9,style="mutable_labyrinth")
    state=initial_state(world)
    closed=[entry["name"] for entry in options(world,state)
            if entry["name"] in ("north","east","south","west")
            and not entry["available"]]
    if not closed:
        state=take_action(world,state,"wait")
        closed=[entry["name"] for entry in options(world,state)
                if entry["name"] in ("north","east","south","west")
                and not entry["available"]]
    assert closed
    direction=closed[0]
    vector={"north":(0,-1),"east":(1,0),
            "south":(0,1),"west":(-1,0)}[direction]
    goal=(state.realm,state.x+vector[0],state.y+vector[1])
    result=compare_solvers(world,goal,starting_state=state,
                           budget=3000,horizon=24)
    assert result["both_confirmed"]
    assert result["bfs"]["actual_turns"]>=2
    assert replay(world,tuple(result["bfs"]["steps"]),
                  starting_state=state).x==goal[1]


def test_solvers_are_optional_even_if_the_game_has_no_goal_or_ending():
    sandbox=create_world(world_id=9,style="mutable_labyrinth")
    assert not sandbox.includes_goal
    waypoint=solve(sandbox,(0,3,2),method="astar",budget=3000,horizon=24)
    assert waypoint.reachable_in_bound
    assert not waypoint.ending_is_required
    assert "optional waypoint" in waypoint.claim
    assert verify_proof(sandbox,waypoint)["verified"]


def test_unbounded_original_world_is_not_falsely_declared_unreachable_by_search_limit():
    world=create_world(world_id=42,style="mutable_labyrinth")
    distant=(0,20,20)
    budgeted=solve(world,distant,method="astar",budget=200,horizon=10)
    assert not budgeted.reachable_in_bound
    assert budgeted.steps==()
    assert "optional waypoint" in budgeted.claim


def test_player_specific_temporal_route_respects_actual_prior_game_history():
    world=create_world(world_id=77,variant=4,style="shifting_dungeon")
    player=replay(world,("north","wait","forage","rest"))
    target=(0,player.x+2,player.y+1)
    report=solve(world,target,starting_state=player,
                 method="bfs",budget=3000,horizon=30)
    assert report.start_digest==player.history_digest
    assert report.start_position==(player.realm,player.x,player.y)
    assert report.reachable_in_bound
    assert replay(world,report.steps,starting_state=player).history_digest==(
        report.replay_digest)
    assert verify_proof(world,report,starting_state=player)["verified"]


@pytest.mark.parametrize("invalid",[
    {"method":"teleport_without_gameplay"},
    {"budget":99},{"budget":10001},{"budget":True},
    {"horizon":0},{"horizon":73},{"horizon":True},
])
def test_dynamic_maze_solver_has_strict_budget_and_real_method_bounds(invalid):
    world=create_world(world_id=0,style="mutable_labyrinth")
    with pytest.raises(ValueError):
        solve(world,(0,2,2),**invalid)


def test_dynamic_maze_solver_does_not_claim_water_vehicle_physics_or_pretend_nonmaze():
    world=create_world(world_id=0,style="creative_sandbox")
    with pytest.raises(ValueError):
        changing_doors(world)
    with pytest.raises(ValueError):
        solve(world,(0,2,2))


def test_original_temporal_solver_rejects_unreachable_realm_without_portal():
    world=create_world(world_id=2026,style="rotating_tower")
    assert world.realms>=3
    with pytest.raises(ValueError):
        solve(world,(1,1,1))
