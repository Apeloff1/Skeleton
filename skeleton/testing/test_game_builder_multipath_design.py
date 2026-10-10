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
    assert route_revisits(replay) == 1
    assert replay.steps == direct.steps + 2


def test_turn_metric_distinguishes_direct_route_from_detour():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    direct = solve_route(p)
    assert route_turns(direct) == 0
    detour = evaluate_route(p, ("down", "right", "up") + ("right",) * 5)
    assert route_turns(detour) == 3
    assert detour.steps == 8


def test_corridor_overlap_is_symmetric_and_identity_exact():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    a = solve_route(p)
    b = solve_route(p, algorithm="dijkstra",
                    edge_penalties={((1, 1), (2, 1)): 100})
    assert route_overlap_ppm(a, a) == 1_000_000
    assert 0 <= route_overlap_ppm(a, b) < 1_000_000
    assert route_overlap_ppm(a, b) == route_overlap_ppm(b, a)
    with pytest.raises(MultipathError, match="same verified world"):
        route_overlap_ppm(a, solve_route(RouteProblem.from_rows(HAZARD_LEVEL)))


def test_novelty_is_exact_complement_of_overlap():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    a = solve_route(p)
    b = solve_route(p, algorithm="dijkstra",
                    edge_penalties={((1, 1), (2, 1)): 30})
    assert route_diversity_ppm(a, a) == 0
    assert route_diversity_ppm(a, b) == 1_000_000 - route_overlap_ppm(a, b)


def test_route_portfolio_finds_real_distinct_routes_and_caps_work():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    portfolio = route_portfolio(p, max_routes=4)
    assert 2 <= len(portfolio) <= 4
    assert portfolio == route_portfolio(p, max_routes=4)
    assert len({route.actions for route in portfolio}) == len(portfolio)
    assert all(evaluate_route(p, r.actions).positions == r.positions
               for r in portfolio)
    assert any(route_diversity_ppm(portfolio[0], route) > 0
               for route in portfolio[1:])
    with pytest.raises(MultipathError):
        route_portfolio(p, max_routes=0)


def test_walkable_cell_catalog_distinguishes_hazard_cost():
    p = RouteProblem.from_rows(HAZARD_LEVEL)
    safe = walkable_cells(p)
    all_cells = walkable_cells(p, include_hazards=True)
    assert (3, 1) not in safe and (3, 1) in all_cells
    assert len(all_cells) == len(safe) + 1
    assert all(p.tile(point) != "#" for point in all_cells)

