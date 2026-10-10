"""Behavioral regressions for the independently replayable multi-route solvers."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.game_builder.multipath_design import (
    MultipathError, RouteProblem, evaluate_route, solve_route,
)

OPEN_LEVEL = (
    "#########",
    "#S..C..G#",
    "#.......#",
    "#.#.#.#.#",
    "#...H...#",
    "#.#.#.#.#",
    "#.......#",
    "#.......#",
    "#########",
)

HAZARD_LEVEL = (
    "#########",
    "#S.H.C.G#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#########",
)


def test_objective_state_bfs_is_deterministic_and_replayable():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    first = solve_route(problem)
    assert first == solve_route(problem)
    assert first.problem_digest == problem.digest
    assert first.collectible_order == ((4, 1),)
    assert first.positions[0] == problem.start
    assert first.positions[-1] == problem.goal
    assert first.steps == 6
    assert first.cost == first.steps
    assert first.hazard_visits == 0
    assert first.digest == solve_route(problem).digest
    assert evaluate_route(problem, first.actions).positions == first.positions


def test_weighted_solver_uses_policy_to_choose_safe_detour():
    problem = RouteProblem.from_rows(HAZARD_LEVEL)
    risky = solve_route(problem, algorithm="dijkstra", allow_hazards=True,
                        hazard_cost=0)
    safe = solve_route(problem, algorithm="dijkstra", allow_hazards=True,
                       hazard_cost=20)
    assert risky.steps == 6
    assert risky.hazard_visits == 1
    assert safe.hazard_visits == 0
    assert safe.steps > risky.steps
    assert safe.cost < risky.cost + 20
    assert safe == solve_route(problem, algorithm="dijkstra",
                               allow_hazards=True, hazard_cost=20)
    assert solve_route(problem).hazard_visits == 0


def test_invalid_route_replay_never_claims_completion():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    for actions in ((), ("right",), ("left",), ("invent",)):
        with pytest.raises(MultipathError):
            evaluate_route(problem, actions)


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[:-1],
    lambda rows: (".........",) + rows[1:],
    lambda rows: rows[:2] + ("#S.....G#",) + rows[3:],
    lambda rows: rows[:1] + ("#S.....G#",) + rows[2:],
    lambda rows: rows[:1] + ("#S..C..?#",) + rows[2:],
])
def test_grid_admission_rejects_broken_boundaries_and_objectives(mutation):
    with pytest.raises(MultipathError):
        RouteProblem.from_rows(mutation(OPEN_LEVEL))


def test_explicit_search_budget_fails_closed():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    with pytest.raises(MultipathError, match="expansion budget"):
        solve_route(problem, max_expansions=1)
    with pytest.raises(MultipathError, match="BFS admits only"):
        solve_route(problem, algorithm="bfs", allow_hazards=True)
    with pytest.raises(MultipathError, match="invalid state expansion"):
        solve_route(problem, max_expansions=True)


def test_edge_penalty_influences_route_and_cannot_reference_walls():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    costly = {((1, 1), (2, 1)): 100}
    result = solve_route(problem, algorithm="dijkstra", edge_penalties=costly)
    assert result.actions[0] == "down"
    assert result.cost < 100
    with pytest.raises(MultipathError, match="non-walkable transition"):
        solve_route(problem, algorithm="dijkstra",
                    edge_penalties={((0, 0), (0, 1)): 3})
    with pytest.raises(MultipathError, match="invalid edge penalty"):
        solve_route(problem, algorithm="dijkstra",
                    edge_penalties={((1, 1), (2, 1)): -1})

def test_directed_route_edge_lineage_is_ordered_and_exact():
    route = solve_route(RouteProblem.from_rows(OPEN_LEVEL))
    edges = route_edges(route)
    assert len(edges) == route.steps
    assert edges[0][0] == (1, 1)
    assert edges[-1][1] == (7, 1)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in edges)


def test_revisits_count_real_tiles_not_length_surrogates():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    direct = solve_route(p)
    loop = ("down", "up") + direct.actions
    replay = evaluate_route(p, loop)
    assert route_revisits(direct) == 0
    assert route_revisits(replay) == 2
    assert replay.steps == direct.steps + 2

