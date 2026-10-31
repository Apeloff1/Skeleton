"""Route planner profile tests for ground_footpath."""
import pytest
from skeleton.forge.route_planners_v1.ground_footpath import (
    Route, NODES, EDGES, plan, inspect, validate_route,
)


def test_metadata_reports_profile():
    data = inspect()
    assert data["route_id"] == "ground_footpath"
    assert data["edge_count"] == len(EDGES)
    assert data["release_certified"] is False


def test_default_has_valid_path():
    result = plan()
    assert result is not None
    assert result.nodes[0] == "start"
    assert result.nodes[-1] == "goal"
    assert validate_route(result)


def test_path_is_deterministic():
    assert plan() == plan()
    assert plan(danger_weight=9) == plan(danger_weight=9)


def test_same_origin_goal_is_zero_cost():
    route = plan(origin="safehouse", destination="safehouse")
    assert route == Route(("safehouse",), 0, 0, 0, 0)


def test_blocked_goal_returns_none():
    assert plan(blocked=("goal",)) is None


def test_blocked_intermediate_still_finds_alternate():
    path = plan(blocked=("crossroads",))
    assert path is not None
    assert "crossroads" not in path.nodes
    assert validate_route(path, ("crossroads",))


def test_all_intermediates_and_direct_blocked_returns_none():
    assert plan(blocked=("crossroads", "safehouse", "lookout")) is not None
    assert plan(danger_budget=0, energy_budget=0) is None


def test_energy_constraint_enforced():
    path = plan(energy_budget=12)
    if path is not None:
        assert path.energy <= 12


def test_danger_constraint_enforced():
    path = plan(danger_budget=10)
    if path is not None:
        assert path.danger <= 10


def test_weighted_cost_is_exact():
    path = plan(distance_weight=3, danger_weight=4, energy_weight=5)
    assert path is not None
    assert path.cost == 3 * path.distance + 4 * path.danger + 5 * path.energy


def test_invalid_origin_fails_closed():
    with pytest.raises(ValueError):
        plan(origin="unknown")


def test_invalid_destination_fails_closed():
    with pytest.raises(ValueError):
        plan(destination="../secret")


@pytest.mark.parametrize("bad", [-1, None, True, 1.5, 100001])
def test_invalid_budget_rejected(bad):
    with pytest.raises(ValueError):
        plan(energy_budget=bad)


def test_zero_objective_rejected():
    with pytest.raises(ValueError):
        plan(distance_weight=0, danger_weight=0, energy_weight=0)


def test_invalid_blocked_type_rejected():
    with pytest.raises(ValueError):
        plan(blocked=["goal"])


def test_duplicate_blocked_nodes_rejected():
    with pytest.raises(ValueError):
        plan(blocked=("goal", "goal"))


def test_client_forged_route_rejected():
    valid = plan()
    assert valid is not None
    forged = Route(valid.nodes, valid.distance + 1, valid.danger, valid.energy, valid.cost)
    assert not validate_route(forged)


def test_route_containing_illegal_edge_rejected():
    illegal = Route(("start", "lookout"), 0, 0, 0, 0)
    assert not validate_route(illegal)


def test_nonroute_object_rejected():
    assert validate_route(None) is False
